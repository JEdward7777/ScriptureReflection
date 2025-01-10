"""
I change my mind about the format deciding that I wanted a vref reference and the source in the
format.  This file fixes the old files which do not have this in them.
"""

import os
import yaml
import utils

def run_config( config: dict, ebible_dir: str ) -> None:
    """
    This loads a file and fixes it.
    """
    if config['active']:
        print( f"Injecting vref and source into {config['file']}" )

        source = config['source']
        source_content = utils.load_file_to_list( os.path.join( ebible_dir, 'corpus',
            source + '.txt' ) )

        verses = utils.load_jsonl( config['file'] )
        vrefs = utils.load_file_to_list( os.path.join( ebible_dir, 'metadata',
            'vref.txt' ) )
        for i, verse in enumerate( verses ):
            if verse:
                verse['vref'] = vrefs[i]
                verse['source'] = source_content[i]
        utils.save_jsonl( config['file'], verses )


def main():
    """
    This is the main entry point for the script.
    """
    #load the config.
    with open( 'inject_vref_and_source.yaml', encoding='utf-8' ) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    for specific_config in config['configs'].values():
        run_config( specific_config, config['global_configs']['ebible_dir'] )


if __name__ == '__main__':
    main()
