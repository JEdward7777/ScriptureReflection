"""
Converts the generated bible into different consumable formats.
"""
import os
import time


import output_formatters.usfm
import output_formatters.ryder_jsonl_format
import output_formatters.sorted_report
import output_formatters.markdown
import output_formatters.html_report


USFM_NAME = output_formatters.usfm.USFM_NAME


#from output_formatters.usfm import USFM_NAME  # Ensure the import statement correctly references the module and attribute


def main():
    """
    Main function.
    """
    #Disable warning about Exception being too broad.
    # pylint: disable=W0718

    #run through all the different jsonl files in the output folder and convert them to different
    #formats

    for file in os.listdir("output"):
        if file.endswith(".jsonl"):

            try:
                output_formatters.sorted_report.run(file)
            except Exception as ex:
                print( f"Problem running convert_to_sorted_report for {file}: {ex}")
                time.sleep( 5 )

            try:
                output_formatters.ryder_jsonl_format.run(file)
            except Exception as ex:
                print( f"Problem running convert_to_ryder_jsonl_format for {file}: {ex}")
                time.sleep( 5 )

            try:
                output_formatters.usfm.run(file)
            except Exception as ex:
                print( f"Problem running convert_to_usfm for {file}: {ex}")
                time.sleep( 5 )

            try:
                output_formatters.markdown.run(file)
            except Exception as ex:
                print( f"Problem running convert_to_markdown for {file}: {ex}")
                time.sleep( 5 )

            try:
                output_formatters.before_and_after.run(file)
            except Exception as ex:
                print( f"Problem running create_before_and_after_output for {file}: {ex}")
                time.sleep( 5 )

            #try:
            if True:
                output_formatters.pdf_report.run(file)
            #except Exception as ex:
            #    print( f"Problem running convert_to_report for {file}: {ex}")
            #    time.sleep( 5 )

            #try
            if True:
                output_formatters.html_report.run(file)
            #except Exception as ex:
            #    print( f"Problem running convert_to_html_report for {file}: {ex}")
            #    time.sleep( 5 )

if __name__ == "__main__":
    main()

    #convert_to_sorted_report( "open_bible_nueva_Biblia.jsonl" )

    print( "Done!" )
