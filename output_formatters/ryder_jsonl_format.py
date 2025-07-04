import os
import yaml
from datetime import datetime
from openai import OpenAI
from pydantic import BaseModel
import utils
from collections import OrderedDict

def run(file):
    """
    Converts the format into a format used by Ryder in his repo
    https://github.com/ryderwishart/swarm
    """

    original_config = None
    with open( 'easy_draft.yaml', encoding='utf-8' ) as f:
        easy_draft_yaml = yaml.load(f, Loader=yaml.FullLoader)
    for config in easy_draft_yaml['configs'].values():
        if config['output'] == os.path.splitext(file)[0]:
            original_config = config

    ebible_dir = easy_draft_yaml['global_configs']['ebible_dir']

    #get modified date of os.path.splitext(file)[0]
    modified_date = datetime.fromtimestamp(os.path.getmtime(f"output/{file}"))

    if original_config:
        source = original_config['source']
        source_content = utils.load_file_to_list( os.path.join( ebible_dir, 'corpus',
            source + '.txt' ) )


        original_content = utils.load_jsonl(f"output/{file}")

        #load output_formats.yaml
        this_config = get_config_for( file )

        #check if the filename sans path and extension is in config.config
        if this_config:
            print( f"converting {file} to ryder format" )

            translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
            reference_key = this_config.get( 'reference_key', ['vref'] )
            translation_time_key = this_config.get( 'translation_time_key', ['translation_time'] )


            output_file = this_config.get( 'output_file', os.path.splitext(file)[0] )


            if not os.path.exists("output/ryder_format"):
                os.makedirs("output/ryder_format")
            with open( f"output/ryder_format/{output_file}.jsonl", "w", encoding="utf-8") as f_out:
                for i, in_verse in enumerate(original_content):
                    if in_verse:
                        out_verse = OrderedDict()
                        for key,value in this_config['ryder_format']['outputs'].items():
                            out_verse[key] = value
                        out_verse["original"]      = source_content[i]
                        out_verse["translation"]   = utils.look_up_key( in_verse, translation_key )
                        #round to two digits.
                        out_verse['translation_time'] = \
                            round( utils.look_up_key( in_verse, translation_time_key ), 2)
                        out_verse['model']         = original_config['model']
                        out_verse['calver']        = modified_date.strftime("%Y.%m.%d")
                        out_verse['id']            = utils.look_up_key( in_verse, reference_key )

                        f_out.write(json.dumps(out_verse, ensure_ascii=False) + "\n")