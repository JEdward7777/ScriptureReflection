import os
import json
import easy_draft
from collections import OrderedDict
import yaml
from datetime import datetime


def convert_to_ryder_jsonl_format(file):

    original_config = None
    with open( 'easy_draft.yaml', encoding='utf-8' ) as f:
        easy_draft_yaml = yaml.load(f, Loader=yaml.FullLoader)
    for config in easy_draft_yaml['configs'].values():
        if config['output'] == os.path.splitext(file)[0]:
            original_config = config

    ebible_dir = easy_draft_yaml['global_configs']['ebible_dir']
    source = original_config['source']
    source_content = easy_draft.load_file_to_list( os.path.join( ebible_dir, 'corpus', source + '.txt' ) )

    #get modified date of os.path.splitext(file)[0]
    modified_date = datetime.fromtimestamp(os.path.getmtime(f"output/{file}"))

    if original_config:


        original_content = list(map(json.loads, easy_draft.load_file_to_list(f"output/{file}")))

        #load output_formats.yaml
        with open( 'output_formats.yaml', encoding='utf-8' ) as f:
            output_formats_yaml = yaml.load(f, Loader=yaml.FullLoader)

        #check if the filename sans path and extension is in config.config
        if os.path.splitext(file)[0] in output_formats_yaml['configs']:
            print( f"converting {file} to ryder format" )
            this_config = output_formats_yaml['configs'][os.path.splitext(file)[0]]

            if not os.path.exists("output/ryder_format"):
                os.makedirs("output/ryder_format")
            with open( f"output/ryder_format/{file}", "w", encoding="utf-8") as f_out:
                for i, in_verse in enumerate(original_content):
                    if in_verse:
                        out_verse = OrderedDict()
                        for key,value in this_config['ryder_format']['outputs'].items():
                            out_verse[key] = value
                        out_verse["original"]         = source_content[i]
                        out_verse["translation"]      = in_verse['fresh_translation']['text']
                        #round to two digits.
                        out_verse['translation_time'] = round(in_verse['translation_time'], 2)
                        out_verse['model']            = original_config['model']
                        out_verse['calver']           = modified_date.strftime("%Y.%m.%d")
                        out_verse['id']               = in_verse['fresh_translation']['reference']

                        f_out.write(json.dumps(out_verse, ensure_ascii=False) + "\n")



def main():
    #run through all the different jsonl files in the output folder and convert them to different formats

    for file in os.listdir("output"):
        if file.endswith(".jsonl"):
            convert_to_ryder_jsonl_format(file)

    print( "Done!" )

if __name__ == "__main__":
    main()