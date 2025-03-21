import utils
import os
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict

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

        collected_verse_text = OrderedDict()
        def add_text( verse_id, verse_text ):
            text = collected_verse_text.get( verse_id, "" )
            if text: text += "\n"
            text += verse_text
            collected_verse_text[ verse_id ] = text

        def get_full_text(element):
            """ Recursively get text from an element, including all child elements. """
            text = element.text or ""
            for child in element:
                text += get_full_text(child) + (child.tail or "")
            text += element.tail
            return text.strip()

        xml_folder = settings['folder']
        #iterate through the xml files that have usx extensions:
        for xml_file in os.listdir(xml_folder):
            if xml_file.lower().endswith('.usx'):
                print(f"Loading {xml_file}")
                usx_file = os.path.join(xml_folder, xml_file)
                
                # Load the XML file
                tree = ET.parse(usx_file)
                root = tree.getroot()

                current_reference = [""]

                # Recursively iterate through all tags
                def process_element(element):
                    if element.tag == 'verse':
                        sid = element.get('sid')
                        eid = element.get('eid')
                        if sid is not None:
                            current_reference[0] = sid
                        if eid is not None:
                            assert current_reference[0] == eid, "eid should be the sid that was in effect"
                            current_reference[0] = ""
                    if current_reference[0] and element.text and element.text.strip():
                        add_text( current_reference[0], element.text.strip() )
                        
                    for child in element:
                        process_element(child)

                    if current_reference[0] and element.tail and element.tail.strip():
                        add_text( current_reference[0], element.tail.strip() )
                
                process_element(root)

        result = []
        for vref, verse_text in collected_verse_text.items():
            new_verse = {}
            utils.set_key( new_verse, reference_key, vref )
            utils.set_key( new_verse, translation_key, verse_text )
            result.append(new_verse)
        result = sort_verses( result, reference_key )
        return result
    elif settings['format'] == 'vref':
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

    verse_to_cluster = defaultdict( lambda: VerseCluster() )

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

        #now save it out.
        utils.save_jsonl( os.path.join( "output", f"{name}.jsonl" ), combined )
        print( "loaded")


    
if __name__ == '__main__':
    main()
    print( "Done" )