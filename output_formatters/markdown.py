import os
from datetime import datetime
from collections import defaultdict

from format_utilities import get_config_for
import utils

def run(file):
    """
    Converts the format to be readable as MarkDown.
    """
    print( f"converting {file} to markdown format" )


    original_content = utils.load_jsonl(f"output/{file}")

    modified_date = datetime.fromtimestamp(os.path.getmtime(f"output/{file}"))

    this_config = get_config_for( file )

    if this_config:
        translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
        translation_comment_key = this_config.get( 'translation_comment_key', ['translation_notes'] )
        reference_key = this_config.get( 'reference_key', ['vref'] )
        override_key = this_config.get( 'override_key',
            ['forming_verse_range_with_previous_verse'] )
        output_file = this_config.get( 'output_file', os.path.splitext(file)[0] )


        #Mark which verse should be dropped because they are overwritten by ranges.
        verse_to_drop = utils.get_overridden_references( original_content, reference_key,
            override_key )

        #run through the content and sort it out into books.
        book_to_chapter_to_verses = defaultdict( lambda: defaultdict( lambda: [] ) )
        for verse_index,verse in enumerate(original_content):
            if 'start_line' in this_config['markdown_format']:
                if verse_index < this_config['markdown_format']['start_line']-1:
                    continue

            if 'start_line' in this_config:
                if verse_index < this_config['start_line']-1:
                    continue

            if 'end_line' in this_config['markdown_format']:
                if verse_index > this_config['markdown_format']['end_line']-1:
                    break

            if 'end_line' in this_config:
                if verse_index > this_config['end_line']-1:
                    break

            if verse:
                #reference = verse["fresh_translation"]["reference"]
                reference = utils.look_up_key(verse, reference_key)
                if " " in reference:
                    if reference not in verse_to_drop:
                        book, chapter_num, _ = utils.split_ref( reference )
                        book_to_chapter_to_verses[book][chapter_num].append(verse)
                    else:
                        print( "Dropping verse", utils.look_up_key(verse, reference_key) )

        output_folder = f"output/markdown_format/{output_file}"
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        with open(f"{output_folder}/README.md", "w", encoding='utf-8') as index:
            index.write( f"# {output_file}\n\n" )
            index.write( "| Key | Value |\n")
            index.write( "|:---:|:-----:|\n")
            for key,value in this_config['markdown_format']['outputs'].items():
                index.write( f"|{key}|{value}|\n")

            index.write( f"|translation date|{modified_date.strftime('%Y.%m.%d')}|\n")
            index.write( "\n")

            index.write( "# Books\n" )
            for book in book_to_chapter_to_verses.keys():
                index.write( f"- [{book}]({book}/README.md)\n" )

        for book,chapter_to_verses in book_to_chapter_to_verses.items():
            if not os.path.exists(f"{output_folder}/{book}/README.md"):
                os.makedirs(f"{output_folder}/{book}", exist_ok=True)
            with open(f"{output_folder}/{book}/README.md", "w", encoding='utf-8') as book_index:
                book_index.write( f"# {book}\n\n" )
                book_index.write( "[Book List](../README.md)\n\n" )
                book_index.write( "# Chapters\n" )
                for chapter_num,verses in chapter_to_verses.items():
                    book_index.write( f"- [{book} {chapter_num}](./chapter_{chapter_num}.md)\n" )


                    with open( f"{output_folder}/{book}/chapter_{chapter_num}.md",
                                "w", encoding='utf-8') as chapter_out:
                        chapter_out.write( f"# {book} {chapter_num}\n" )

                        chapter_out.write( "[Book List](../README.md)\n\n" )

                        if int(chapter_num)-1 in chapter_to_verses:
                            chapter_out.write(f"[<-](./chapter_{str(int(chapter_num)-1)}.md) ")
                        for other_chapter_num in chapter_to_verses.keys():
                            if other_chapter_num != chapter_num:
                                chapter_out.write(
                                    f"[{other_chapter_num}](./chapter_{other_chapter_num}.md) ")
                            else:
                                chapter_out.write(f"{other_chapter_num} ")
                        if int(chapter_num)+1 in chapter_to_verses:
                            chapter_out.write(f"[->](./chapter_{str(int(chapter_num)+1)}.md)")

                        chapter_out.write( "\n\n" )


                        chapter_out.write( "| Reference | Verse | Translation Notes |\n")
                        chapter_out.write( "|:---------:|-------|-------------------|\n")

                        for verse in verses:
                            vref = utils.look_up_key(verse, reference_key)
                            translation = utils.look_up_key(verse, translation_key).\
                                    replace('\n', '<br>')
                            comment = utils.look_up_key(verse, translation_comment_key,"",none_is_valid=False).\
                                    replace('\n', '<br>')
                            chapter_out.write(
                                f"|{vref}|{translation}|" +
                                f"{comment}|\n")


                        chapter_out.write( "\n\n")
                        if int(chapter_num)-1 in chapter_to_verses:
                            chapter_out.write(f"[<-](./chapter_{str(int(chapter_num)-1)}.md) ")
                        for other_chapter_num in chapter_to_verses.keys():
                            if other_chapter_num != chapter_num:
                                chapter_out.write(
                                    f"[{other_chapter_num}](./chapter_{other_chapter_num}.md) ")
                            else:
                                chapter_out.write(f"{other_chapter_num} ")
                        if int(chapter_num)+1 in chapter_to_verses:
                            chapter_out.write(f"[->](./chapter_{str(int(chapter_num)+1)}.md)")

