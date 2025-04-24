import os
from lxml import etree
from collections import OrderedDict, defaultdict
from usfm_grammar import USFMParser
import copy

import utils
import output_formats



def sort_verses( verses, reference_key ):

    def verse_sort_key_func( verse ):
        found_index = -1
        book, chapter, verse = utils.split_ref( utils.look_up_key( verse, reference_key ))
        for i, key in enumerate( output_formats.USFM_NAME.keys() ):
            if book in key:
                found_index = i
                break
        assert found_index != -1, "Didn't find the book name in known book names"
        if isinstance(verse, str) and '-' in verse:
            verse = int(verse.split('-')[0])

        return (found_index, chapter, verse)


    sorted_verses = sorted( verses, key=verse_sort_key_func )
    return sorted_verses


def load_format( settings, reference_key, translation_key ):
    if settings['format'] == 'USX':
        result = []
        import_folder = settings['folder']
        #iterate through the xml files that have usx extensions:
        for filename in os.listdir(import_folder):
            if filename.lower().endswith('.usx'):
                print(f"Loading {filename}")
                usx_file = os.path.join(import_folder, filename)
                
                # Load the XML file
                #https://pypi.org/project/usfm-grammar/#:~:text=USX%20TO%20USFM%2C%20USJ%20OR%20TABLE
                with open( usx_file, 'r', encoding='utf-8' ) as f:
                    usx_str = f.read()
                    usx_obj = etree.fromstring(usx_str)

                    my_parser = USFMParser(from_usx=usx_obj)

                    dict_output = my_parser.to_biblenlp_format( ignore_errors=settings.get('ignore_errors', True) )

                    for vref,text in zip( dict_output['vref'], dict_output['text'] ):
                        new_verse = {}
                        utils.set_key(new_verse, reference_key, vref)
                        utils.set_key(new_verse, translation_key, text)
                        result.append(new_verse)

        result = sort_verses( result, reference_key )
        return result
    elif settings['format'] == 'usfm':
        result = []
        import_folder = settings['folder']
        #iterate through the usfm files:
        for filename in os.listdir(import_folder):
            if filename.lower().endswith('.usfm') or filename.lower().endswith('.sfm'):
                print(f"Loading {filename}")
                full_filename = os.path.join(import_folder, filename)
                
                # Load the usfm file
                #https://pypi.org/project/usfm-grammar/#:~:text=USX%20TO%20USFM%2C%20USJ%20OR%20TABLE
                with open( full_filename, 'r', encoding='utf-8' ) as f:
                    usfm_string = f.read()

                    my_parser = USFMParser(usfm_string)

                    dict_output = my_parser.to_biblenlp_format( ignore_errors=settings.get('ignore_errors', True) )

                    for vref,text in zip( dict_output['vref'], dict_output['text'] ):
                        new_verse = {}
                        utils.set_key(new_verse, reference_key, vref)
                        utils.set_key(new_verse, translation_key, text)
                        result.append(new_verse)

        result = sort_verses( result, reference_key )
        return result
    elif settings['format'] == 'biblenlp':
        vref_file = settings['vref']
        source_file = settings['source']
        vrefs = utils.load_file_to_list( vref_file )
        source = utils.load_file_to_list( source_file )
        result = []
        for vref, source_verse in zip( vrefs, source ):
            if source_verse:
                assert vref, "missing vref for verse"
                new_verse = {}
                utils.set_key( new_verse, reference_key, vref )
                utils.set_key( new_verse, translation_key, source_verse )
                result.append(new_verse)
        #result = sort_verses( result, reference_key, translation_key )
        return result

    assert False, f"Unrecognized format {settings['format']}"

def merge_source_and_target( settings, source, target, reference_key, source_key, translation_key ):
    #so to make it so that both the source adn the target can be ranges,
    #what I will do is do the group thing where there
    #is a leader which is in change of each group,
    #and then we will go through each verse injecting
    #their contents up into the leader and then
    #we collect all the leaders and spit out the content.
    class VerseCluster:
        parent_ptr = None
        def connect( self, other ):
            self_parent = self.get_parent()
            other_parent = other.get_parent()
            if self_parent != other_parent:
                self_parent.parent_ptr = other_parent

        def get_parent( self ):
            if self.parent_ptr is None:
                return self

            self.parent_ptr = self.parent_ptr.get_parent()
            return self.parent_ptr

    verse_to_cluster = defaultdict( VerseCluster )

    for v in source + target:
        vref = utils.look_up_key( v, reference_key )
        book, chapter, verse = utils.split_ref( vref )
        if isinstance( verse, str ) and '-' in verse:
            start_verse, end_verse = [int(x) for x in verse.split('-')]
            cluster = verse_to_cluster[(book,chapter,start_verse)].get_parent()
            for verse_count in range(start_verse+1, end_verse+1):
                cluster.connect(verse_to_cluster[(book,chapter,verse_count)])
        else:
            #just touch it in the defaultdict.
            verse_to_cluster[(book,chapter,verse)]

    hashed_results = OrderedDict()

    for side, side_key in [[source,source_key], [target,translation_key]]:
        for v in side:
            vref = utils.look_up_key( v, reference_key )
            book, chapter, start_verse, end_verse = utils.split_ref2( vref )
            cluster = verse_to_cluster[(book,chapter,start_verse)].get_parent()
            if cluster not in hashed_results:
                hashed_results[cluster] = {}
            merged_verse = hashed_results[cluster]
            _, _, existing_start, existing_end = utils.split_ref2( utils.look_up_key( merged_verse, reference_key, default=vref))
            start_verse = min( start_verse, existing_start )
            end_verse = max( end_verse, existing_end )
            if start_verse != end_verse:
                utils.set_key( merged_verse, reference_key, f"{book} {chapter}:{start_verse}-{end_verse}")
            else:
                utils.set_key( merged_verse, reference_key, f"{book} {chapter}:{start_verse}" )

            text = utils.look_up_key( merged_verse, side_key, "" )
            if text: text += "\n"
            text += utils.look_up_key( v, side_key )
            utils.set_key( merged_verse, side_key, text )

    result = list(hashed_results.values())
    result = sort_verses( result, reference_key )

    #now see if there are not any white listed verses which have a
    # target and not a source or the other way around.
    for verse_obj in result:
        vref = utils.look_up_key( verse_obj, reference_key )
        source_text = utils.look_up_key( verse_obj, source_key )
        target_text = utils.look_up_key( verse_obj, translation_key )
        book, chapter, verse_num = utils.split_ref( vref )
        missing_white_list = settings.get( 'missing_white_list', [] )
        missing_level = settings.get( 'missing_level', 'error' )
        if book not in missing_white_list and vref not in missing_white_list:
            if target_text:
                if missing_level == 'error':
                    assert source_text, f"For {vref} missing source text"
                else:
                    if not source_text:
                        print( f"For {vref} missing source text" )
            if source_text:
                if missing_level == 'error':
                    assert target_text, f"For {vref} missing target text"
                else:
                    if not target_text:
                        print( f"For {vref} missing target text" )
                        
    

    return result
   
            


def main():
    configs = utils.load_yaml_configuration( 'input_formats.yaml' )['configs']

    for name,config in configs.items():
        if not config.get('active', True):
            continue

        reference_key = config.get('reference_key'  , ['vref'])
        translation_key = config.get('translation_key', ['fresh_translation','text'] )
        source_key = config.get('source_key'   , ['source'])
        input_target  = load_format( config['input_target'], 
                                     reference_key,
                                     translation_key )
        input_source  = load_format( config['input_source'],
                                     reference_key,
                                     source_key)
        
        combined = merge_source_and_target( config.get('merge',{}), input_source, input_target, reference_key, source_key, translation_key )

        combined = utils.normalize_ranges( combined, reference_key, translation_key, source_key )

        #now save it out.
        utils.save_jsonl( os.path.join( "output", f"{name}.jsonl" ), combined )
        print( "loaded")


    
if __name__ == '__main__':
    main()
    print( "Done" )