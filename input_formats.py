import os
import copy, re
from lxml import etree
from collections import OrderedDict, defaultdict
from usfm_grammar import USFMParser

import utils
import output_formats


def chop_with_regex( content, regex ):
    last_capture = None

    result = {}

    for capture in re.finditer( regex, content ):
        if last_capture is not None:
            capture_number = int(last_capture.group(1))
            chopped_content = content[last_capture.end()+1:capture.start()]
            result[capture_number] = chopped_content

        last_capture = capture

    capture_number = int(last_capture.group(1))
    chopped_content = content[last_capture.end()+1:]

    result[capture_number] = chopped_content

    return result

def hacked_usfm_parser( text ):
    """The reason for this is that the usfm library I am using keeps on not working,
     so this is a hacked version which will just get the job done even if there are problems.
    """
    #so first chop everything up into chapters.
    chapter_regex = r'\\c (\d+)'
    verse_regex = r'\\v (\d+)'
    book_finder = r'\\toc3 (\w+)'

    book_match = re.search( book_finder, text )
    book_name = book_match.group(1).upper()
    
    chapter_content = chop_with_regex( text, chapter_regex )

    vref = []
    text = []

    reg_exp_to_drop = [ r'\\s\d+', r'\\p', r'\\q(\d+)?', r'\\m', r'\\f (.*)\\f\*', r'\\b',
        r'\\f (.*)\\fqa', r'\\1', r'\\nb']

    for chapter_number, chapter_content in chapter_content.items():
        verse_content = chop_with_regex( chapter_content, verse_regex )

        for verse_number, verse_content in verse_content.items():
            for reg_exp in reg_exp_to_drop:
                verse_content = re.sub( reg_exp, '', verse_content )

            if '\\' in verse_content:
                print( f"Found \\ in {verse_content}" )
            
            vref.append( f"{book_name} {chapter_number}:{verse_number}" )
            text.append( verse_content )

    return {'vref':vref, 'text':text }


    #then chop the chapters into verses.
    #Then try and strip out all misc stuff.


def sort_verses( verses, reference_key ):

    def verse_sort_key_func( verse ):
        found_index = -1
        book, chapter, verse = utils.split_ref( utils.look_up_key( verse, reference_key ))
        for i, key in enumerate( output_formats.USFM_NAME.keys() ):
            if book.upper() in key.upper():
                found_index = i
                break
        assert found_index != -1, f"Didn't find the book \"{book}\" in known book names"
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
    elif settings['format'] == 'hacked_usfm':
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

                    dict_output = hacked_usfm_parser( usfm_string )

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
                        try:
                            utils.split_ref( vref )
                            new_verse = {}
                            utils.set_key(new_verse, reference_key, vref)
                            utils.set_key(new_verse, translation_key, text)
                            result.append(new_verse)
                        except ValueError:
                            #don't include "verses" without parsable
                            #references.
                            print( f"Unparsable reference in {filename}:\n   {vref}: {text}" )
    

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
        #result = sort_verses( result, reference_key )
        return result

    elif settings['format'] == 'sblgnt_txt':

        #find a way to convert book names to the standardized 3 letter code.
        ref_reverse_hash = {}
        for key, value in output_formats.USFM_NAME.items():
            if len( key ) == 3:
                ref_reverse_hash[value] = key
        normalization_hash = {}
        for key, value in output_formats.USFM_NAME.items():
            normalization_hash[ key ] = ref_reverse_hash[ value ]


        import_folder = settings['folder']
        result = []
        #iterate through the txt files in the sblgnt or sblgnt like folder
        for filename in os.listdir(import_folder):
            if filename.lower().endswith('.txt'):
                with open( os.path.join(import_folder, filename), 'r', encoding='utf-8' ) as f:
                    for line in f:
                        if '\t' in line:
                            vref, text = line.split('\t')
                            book, chapter, start_verse, end_verse = utils.split_ref2( vref )
                            if book.upper() not in normalization_hash and book not in normalization_hash:
                                assert False, f"Unknown book name {book} in {filename}"
                            if book in normalization_hash:
                                book = normalization_hash[ book ]
                            elif book.upper() in normalization_hash:
                                book = normalization_hash[ book.upper() ]
                            if start_verse == end_verse:
                                vref = f"{book} {chapter}:{start_verse}"
                            else:
                                vref = f"{book} {chapter}:{start_verse}-{end_verse}"

                            new_verse = {}
                            utils.set_key(new_verse, reference_key, vref.strip().upper())
                            utils.set_key(new_verse, translation_key, text.strip())
                            result.append(new_verse)
        result = sort_verses( result, reference_key )
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