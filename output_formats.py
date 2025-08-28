"""
Converts the generated bible into different consumable formats.
"""
import os
import time
import importlib
import pkgutil

from format_utilities import get_config_for

# Import the usfm module to preserve the USFM_NAME export
import output_formatters.usfm

USFM_NAME = output_formatters.usfm.USFM_NAME


def discover_formatters():
    """
    Dynamically discover all formatter modules in the output_formatters package.
    Returns a list of formatter modules that have a 'run' function.
    """
    formatters = []
    
    # Get the output_formatters package
    import output_formatters
    package_path = output_formatters.__path__
    
    # Iterate through all modules in the package
    for importer, modname, ispkg in pkgutil.iter_modules(package_path):
        if not ispkg:  # Only process modules, not sub-packages
            try:
                # Import the module
                module = importlib.import_module(f'output_formatters.{modname}')
                
                # Check if the module has a 'run' function
                if hasattr(module, 'run') and callable(getattr(module, 'run')):
                    formatters.append((modname, module))
                #     print(f"Discovered formatter: {modname}")
                # else:
                #     print(f"Skipping {modname}: no 'run' function found")
                    
            except Exception as ex:
                print(f"Failed to import formatter {modname}: {ex}")
    
    return formatters


def main( run_everything=True, throw_errors=False ):
    """
    Main function.
    """
    #Disable warning about Exception being too broad.
    # pylint: disable=W0718

    # Discover all available formatters
    formatters = discover_formatters()
    
    if not formatters:
        print("No formatters discovered!")
        return
    else:
        print( f"Discovered {len(formatters)} formatters." )

    #run through all the different jsonl files in the output folder and convert them to different
    #formats
    ran_something = False
    for file in os.listdir("output"):
        if file.endswith(".jsonl"):
            #print(f"Considering file {file}...")

            
            # Run each discovered formatter
            for formatter_name, formatter_module in formatters:

                if not run_everything:
                    this_config = get_config_for( file )
                    if this_config is None: this_config = {}
                    if not this_config.get( 'active', False ):
                        if this_config.get( 'enabled', [] ) is None or formatter_name not in this_config.get( 'enabled', [] ):
                            continue


                try:
                    print(f"Running {formatter_name} formatter on {file}...")
                    formatter_module.run(file)
                    ran_something = True
                except Exception as ex:
                    print(f"Problem running {formatter_name} for {file}: {ex}")
                    if throw_errors:
                        raise
                    else:
                        time.sleep(5)

    if not ran_something:
        print("No formatters run.  Check what is enabled.")

if __name__ == "__main__":
    main()

    #convert_to_sorted_report( "open_bible_nueva_Biblia.jsonl" )

    print( "Done!" )
