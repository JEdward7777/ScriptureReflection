"""
This is a POC for a Streamlit app to allow users to provide feedback on the quality of a
translation. But it is evolving into more, such as editing the translation as well.
"""

import cProfile
#import profile as cProfile
import os
import pstats
import io
import random
import json
import yaml
import streamlit as st
from streamlit.components.v1 import html
import utils
import verse_parsing


def verse_parts( refs ):
    """This takes all the string or ints in refs and returns them all in a single array"""
    out_refs = []
    for ref in refs:
        if isinstance(ref, str):
            for part in ref.split("-"):
                out_refs.append( int(part) )
        elif hasattr(ref, "__iter__"):
            out_refs.extend( verse_parts(ref) )
        else:
            out_refs.append( ref )
    return out_refs


def get_max_verse( *verses ):
    """Return the max verse between this.  Supports verse ranges"""
    return max( verse_parts(verses) )

def get_min_verse( *verses ):
    """Return the min verse between this.  Supports verse ranges"""
    return min( verse_parts(verses) )


def split_ref( reference ):
    """Splits the reference into book, chapter and verse"""
    if " " not in reference:
        return reference, None, None
    last_space_index = reference.rindex(" ")
    book_split = reference[:last_space_index]
    chapter_verse_str = reference[last_space_index+1:]
    if ":" not in chapter_verse_str:
        return book_split, int(chapter_verse_str), None
    chapter_num,verse_num = chapter_verse_str.split(":")
    if "-" not in verse_num:
        return book_split, int(chapter_num), int(verse_num)
    else:
        return book_split, int(chapter_num), verse_num

# Load available outputs
loaded_outputs = [filename.rsplit('.', 1)[0] for filename in os.listdir('./output') if
    filename.endswith(".jsonl")]

#https://py.cafe/maartenbreddels/streamlit-switch-tabs-programmatically
def add_button_tab_switch(button_text, tab_text):
    """Streamlit doesn't allow you to programatically switch tabs, so this
    javascript injection adds that capability"""
    html(f"""<script>
    (() => {{

        let button = [...window.parent.document.querySelectorAll("button")].filter(button => {{
            console.log(">>>", button.innerText)
            return button.innerText.includes("{button_text}")
        }})[0];

        if(button) {{
            button.onclick = () => {{
                var tabGroup = window.parent.document.getElementsByClassName("stTabs")[0]
                const tabButton = [...tabGroup.querySelectorAll("button")].filter(button => {{
                    return button.innerText.includes("{tab_text}")
                }})[0];
                if(tabButton) {{
                    tabButton.click();
                }} else {{
                    console.log("tab button {tab_text} not found")
                }}
            }}
        }} else {{
            console.log("button not found: {button_text}")
        }}
    }})();

    </script>""", height=0)

# Cache the loading of reference data
@st.cache_data
def load_reference_data():
    """Loads the vref data as referenced in the easy_draft.yaml file"""
    with open('easy_draft.yaml', encoding='utf-8') as f:
        easy_draft_yaml = yaml.load(f, Loader=yaml.FullLoader)
    ebible_dir = easy_draft_yaml['global_configs']['ebible_dir']
    return utils.load_file_to_list(os.path.join(ebible_dir, 'metadata', 'vref.txt'))

#@st.cache_data
def cached_to_range(selected_verses, all_verses):
    """Caches the verse parsing to_range function"""
    return verse_parsing.to_range(selected_verses, all_verses)

#@st.cache_data
def load_translation_data(selected_translation):
    """Loads the data for the selected translation."""
    vrefs = load_reference_data()
    filepath = f"./output/{selected_translation}.jsonl"
    with open(filepath, 'r', encoding='utf-8') as file:
        loaded_lines = [json.loads(line) for line in file]
    #loaded_lines = [{**loaded_line, 'vref': vrefs[i]} if loaded_line else
    #    None for i, loaded_line in enumerate(loaded_lines)]
    loaded_lines = [loaded_line if not loaded_line else {**loaded_line, 'vref': vrefs[i]} if 'vref'
        not in loaded_line else loaded_line for i, loaded_line in enumerate(loaded_lines)]
    return loaded_lines

def edit_verse(selected_verse, old_text, new_text, translation_key, translation_comment_key):
    """Edits the verse in the jsonl structure honoring the grading loop verse state rules"""

    #if there is a grade collection for the current verse without the verse it was grading tagged
    #in with it go ahead and copy the translation in there.

    #is there a reflection loops section?
    if 'reflection_loops' in selected_verse:
        reflection_loops = selected_verse['reflection_loops']
        #are there any loops in it?
        if reflection_loops:
            last_reflection_loop = reflection_loops[-1]
            #does it have any grades in it yet?
            if 'grades' in last_reflection_loop:
                grades = last_reflection_loop['grades']
                if grades:
                    #Is the graded_verse put in it yet?
                    if 'graded_verse' not in last_reflection_loop:
                        last_reflection_loop['graded_verse'] = old_text

                        #is there a comment to copy over as well?
                        comment = utils.look_up_key( selected_verse, translation_comment_key )
                        if comment:
                            last_reflection_loop['graded_verse_comment'] = comment

    #now see if there is a finilization flag set.
    if 'reflection_is_finalized' in selected_verse and selected_verse['reflection_is_finalized']:
        selected_verse['reflection_is_finalized'] = False


    #now we can go ahead and update the translation in the verse.
    utils.set_key( selected_verse, translation_key, new_text )
    utils.set_key( selected_verse, translation_comment_key, "" )

def save_translation_data(selected_translation, translation_data):
    """Saves the translation data back out, like when a verse is edited"""
    filepath = f"./output/{selected_translation}.jsonl"
    utils.save_jsonl(filepath, translation_data)

def load_comment_data(selected_translation):
    """Loads the comment data for a selected translation"""
    filepath = f"./output/comments/{selected_translation}.jsonl"
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            loaded_lines = [json.loads(line) for line in file]
        return loaded_lines
    except FileNotFoundError:
        return []

def save_comments(selected_translation,comment_data):
    """Saves the comment data for a selected translation"""
    filepath = f"./output/comments/{selected_translation}.jsonl"
    temp_filepath = f"./output/comments/{selected_translation}~.jsonl"
    if not os.path.exists("./output/comments"):
        os.makedirs("./output/comments")
    with open(temp_filepath, 'w', encoding='utf-8') as file:
        for this_comment in comment_data:
            file.write(json.dumps(this_comment) + "\n")
    os.replace(temp_filepath, filepath)

def get_verse_for_reference( data, book, chapter, verse, overridden_references ):
    """Fetches the verse object for a given reference"""
    vref_to_get = f"{book} {chapter}:{verse}"
    if vref_to_get in overridden_references:
        vref_to_get = overridden_references[vref_to_get]

    for item in data:
        if 'vref' in item and item['vref'] == vref_to_get:
            return item
        if 'vrefs' in item and vref_to_get in item['vrefs']:
            return item

    return None

def get_text_for_reference(data, book, chapter, verse):
    """Fetches the text for a given reference."""
    for item in data:
        b, c, v = split_ref(item['vref'])
        if b == book and c == chapter and v == verse:
            return item['fresh_translation']['text']
    return "Text not found."

def get_source_for_reference(data, book, chapter, verse):
    """Gets the source for a specific reference"""
    for item in data:
        b, c, v = split_ref(item['vref'])
        if b == book and c == chapter and v == verse:
            return item['source']
    return "Source not found."

def get_comments_for_reference( comment_data, book, chapter, verse ):
    """Gets the comments for a specific reference"""
    vref = f"{book} {chapter}:{verse}"

    result = []
    for comment in comment_data:
        if vref in comment['ids']:
            result.append(comment)

    return result

def reference_to_index(data,book,chapter,verse):
    """Fetches the index for a given reference."""
    for i, item in enumerate(data):
        b, c, v = split_ref(item['vref'])
        if b == book and c == chapter and v == verse:
            return i
    return None

def index_to_reference(data, index):
    """Fetches the reference for a given index."""
    try:
        return split_ref(data[index]['vref'])
    except IndexError:
        return None


def main():
    """Main function for the Streamlit app."""
    st.title("Translation Comment Collector")

    # Translation Dropdown
    selected_translation = st.selectbox("Select Translation", loaded_outputs)

    reference_key = ['vref']
    override_key = ['forming_verse_range_with_previous_verse']
    translation_key = ['fresh_translation','text']
    translation_comment_key = ['translation_notes']
    source_key = ['source']


    if selected_translation:
        translation_data = load_translation_data(selected_translation)
    else:
        translation_data = []

    filtered_translation_data = [x for x in translation_data if x]

    if 'selected_translation' not in st.session_state or selected_translation != \
            st.session_state.selected_translation:
        st.session_state.comment_data = load_comment_data(selected_translation)
        st.session_state.selected_verses = []
        st.session_state.selected_translation = selected_translation
        st.session_state.overridden_references = utils.get_overridden_references(
            filtered_translation_data,reference_key,override_key)

    # Tabs
    browse_chapter_tab, browse_verse_tab, add_comments_tab = st.tabs(["Browse Chapter",
        "Browse Verse", "Add Comments"])

    # Initialize session state variables
    if "book" not in st.session_state:
        st.session_state.book = "GEN"
    if "chapter" not in st.session_state:
        st.session_state.chapter = 1
    if "verse" not in st.session_state:
        st.session_state.verse = 1




    def collect_all_references():
        references = []
        for item in filtered_translation_data:
            if 'vrefs' in item:
                references += item['vrefs']
            elif 'vref' in item:
                references.append(item['vref'])
        #unique_references = list(set(references))
        unique_references = list(dict.fromkeys(references))
        return unique_references

    def collect_references_within_range( start_reference, end_reference, all_references ):
        saw_start_book = False
        saw_start_chapter = False
        saw_start_verse = False

        saw_range_end = False

        sb, sc, sv = split_ref(start_reference)
        eb, ec, ev = split_ref(end_reference)

        references = []

        for vref in all_references:
            b, c, v = split_ref(vref)

            if b == eb and (ec is None or c == ec) and (ev is None or v == ev):
                saw_range_end = True
            elif saw_range_end:
                break

            if b == sb:
                saw_start_book = True
                if sc is None or c == sc:
                    saw_start_chapter = True
                    if sv is None or v == sv:
                        saw_start_verse = True
            if saw_start_book and saw_start_chapter and saw_start_verse:
                references.append(vref)

        return references


    def collect_references_with_keyword( keyword ):
        references = []
        for item in filtered_translation_data:
            if not item:
                continue
            if keyword.lower() in item['fresh_translation']['text'].lower():
                references.append(item['vref'])
        return references

    # Add custom CSS for scrolling
    st.markdown("""
        <style>
        .scrollable-container {
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid #ccc;
            padding: 10px;
            background-color: #f9f9f9;
        }
        </style>
        """, unsafe_allow_html=True)

    if filtered_translation_data:

        # Book, Chapter, Verse selectors
        unique_books = list(dict.fromkeys(split_ref(item['vref'])[0] for item in
            filtered_translation_data if 'vref' in item))
        def select_reference( scope, key, init_book=None, init_chapter=None, init_verse=None ):
            num_columns = 3 if scope == "verse" else 2 if scope == "chapter" else 1

            columns = st.columns(num_columns)

            result = ""

            with columns[0]:
                sel_book = st.selectbox("Select Book", unique_books,
                    index=unique_books.index(init_book) if init_book in unique_books else 0,
                    key=f"{key}-book")
                result = sel_book
            if num_columns >= 2:
                with columns[1]:
                    max_chapter = 0
                    min_chapter = float('inf')
                    for item in filtered_translation_data:
                        if not item:
                            continue
                        b, c, _ = split_ref(item['vref'])
                        if b == sel_book:
                            max_chapter = max(max_chapter, c)
                            min_chapter = min(min_chapter, c)

                    if init_chapter is not None:
                        init_chapter = min( max( init_chapter, min_chapter ), max_chapter )
                        sel_chapter = st.number_input("Select Chapter", min_value=min_chapter,
                            max_value=max_chapter, value=init_chapter, key=f"{key}-chapter")
                    else:
                        sel_chapter = st.number_input("Select Chapter", min_value=min_chapter,
                            max_value=max_chapter, key=f"{key}-chapter")
                    result += f" {sel_chapter}"
            if num_columns == 3:
                with columns[2]:
                    max_verse = 0
                    min_verse = float('inf')
                    for item in filtered_translation_data:
                        if not item:
                            continue
                        b, c, v = split_ref(item['vref'])
                        if b == sel_book and c == sel_chapter:
                            max_verse = get_max_verse(max_verse, v)
                            min_verse = get_min_verse(min_verse, v)

                    if min_verse != float('inf'):
                        if init_verse is not None:
                            init_verse = get_min_verse( get_max_verse( init_verse, min_verse ),
                                max_verse )
                            sel_verse = st.number_input("Select Verse", min_value=min_verse,
                                max_value=max_verse, value=init_verse, key=f"{key}-verse")
                        else:
                            sel_verse = st.number_input("Select Verse", min_value=min_verse,
                                max_value=max_verse, key=f"{key}-verse")
                        result += f":{sel_verse}"
                    else:
                        result += ":1"
            return result


        all_references = collect_all_references()


        if "selected_verses" not in st.session_state:
            st.session_state.selected_verses = []

        if "comment_count" not in st.session_state:
            st.session_state.comment_count = 0


        # Browse chapter Tab
        with browse_chapter_tab:
            st.header("Browse Translation by Chapter")
            st.write("Select a book and chapter to view the verses in that chapter.")

            book_before_dropdown = st.session_state.book
            chapter_before_dropdown = st.session_state.chapter

            st.session_state.book, st.session_state.chapter, _ = split_ref(select_reference(
                "chapter", "browse-chapter", init_book=st.session_state.book,
                init_chapter=st.session_state.chapter ))




            max_chapter = None
            min_chapter = None
            for item in filtered_translation_data:
                if not item:
                    continue
                vref = utils.look_up_key( item, reference_key )
                if vref in st.session_state.overridden_references:
                    continue

                b, c, _ = split_ref(item['vref'])
                if b == st.session_state.book and c == st.session_state.chapter:
                    button_text = f"{item['vref']}"
                    if st.button( button_text ):
                        _,_,st.session_state.verse = split_ref(item['vref'])

                    trans_col, source_col = st.columns(2)
                    with trans_col:
                        st.write( item['fresh_translation']['text'] )
                    with source_col:
                        st.write( item['source'] )

                if b == st.session_state.book:
                    if max_chapter is None or c > max_chapter:
                        max_chapter = c
                    if min_chapter is None or c < min_chapter:
                        min_chapter = c



            # Next and Previous buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Previous", key="chapter-prev"):
                    if st.session_state.chapter > min_chapter:
                        st.session_state.chapter -= 1
            with col2:
                pass
            with col3:
                if st.button("Next", key="chapter-next"):
                    if st.session_state.chapter < max_chapter:
                        st.session_state.chapter += 1


            #put the button to tab connections at the bottom because they produce height.
            for item in filtered_translation_data:
                if not item:
                    continue
                b, c, _ = split_ref(item['vref'])
                if b == st.session_state.book and c == st.session_state.chapter:
                    button_text = f"{item['vref']}"
                    add_button_tab_switch( button_text, "Browse Verse" )

            if st.session_state.book != book_before_dropdown or st.session_state.chapter != \
                    chapter_before_dropdown:
                st.rerun()

        # Browse verse Tab
        with browse_verse_tab:
            st.header("Browse Translation by Verse")


            # Use session state for chapter and verse
            book_before_dropdown = st.session_state.book
            chapter_before_dropdown = st.session_state.chapter
            verse_before_dropdown = st.session_state.verse


            st.session_state.book, st.session_state.chapter, st.session_state.verse = split_ref(
                select_reference( "verse", "browse-verse", init_book=st.session_state.book,
                init_chapter=st.session_state.chapter, init_verse=st.session_state.verse ))



            selected_verse = get_verse_for_reference( filtered_translation_data,
                st.session_state.book, st.session_state.chapter, st.session_state.verse,
                st.session_state.overridden_references )

            st.write(f"**{utils.look_up_key( selected_verse, reference_key )}**")

            # Display current reference and text
            reference_text = utils.look_up_key( selected_verse, translation_key )

            edited_verse = st.text_area( "**Translation:**", value=reference_text,
                key="verse-edit" )
            if edited_verse != reference_text:
                edit_verse( selected_verse, reference_text, edited_verse, translation_key,
                    translation_comment_key )
                save_translation_data( selected_translation, translation_data )
                st.rerun()

            #display the source text.
            source_text = utils.look_up_key( selected_verse, source_key )
            st.write( "**Source Text:**")
            st.write( source_text)

            # Next and Previous buttons
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Previous"):
                    if st.session_state.verse > 1:
                        st.session_state.verse -= 1
                    elif st.session_state.chapter > 1:
                        st.session_state.chapter -= 1
                        st.session_state.verse = get_max_verse(split_ref(item['vref'])[2] for
                            item in filtered_translation_data if
                            split_ref(item['vref'])[0] == st.session_state.book and
                            split_ref(item['vref'])[1] == st.session_state.chapter)
            with col2:
                if st.button("Next"):
                    max_verse = get_max_verse(split_ref(item['vref'])[2] for item in
                        filtered_translation_data if
                        split_ref(item['vref'])[0] == st.session_state.book and split_ref(
                        item['vref'])[1] == st.session_state.chapter)
                    if st.session_state.verse < max_verse:
                        st.session_state.verse = st.session_state.verse +1
                    else:
                        next_chapter = st.session_state.chapter + 1
                        if any(split_ref(item['vref'])[1] == next_chapter for item in
                                filtered_translation_data):
                            st.session_state.chapter = next_chapter
                            st.session_state.verse = 1

            book_after_buttons = st.session_state.book
            chapter_after_buttons = st.session_state.chapter
            verse_after_buttons = st.session_state.verse

            if book_before_dropdown != book_after_buttons:
                st.rerun()
            if chapter_before_dropdown != chapter_after_buttons:
                st.rerun()
            if verse_before_dropdown != verse_after_buttons:
                st.rerun()


            verse_history_tab, verse_comments_tab = st.tabs(["Verse History",
                "Verse Comments"])

            with verse_history_tab:
                st.header("Verse History")

                
                if 'reflection_loops' in selected_verse and selected_verse['reflection_loops']:
                    #iterate the reflection loops in reverse.
                    for i,reflection_loop in reversed(list(enumerate(selected_verse['reflection_loops']))):
                        if 'graded_verse' in reflection_loop:
                            if 'average_grade' in reflection_loop:
                                st.write( f"**Version {i+1}**: _(Grade {reflection_loop['average_grade']:.1f})_" )
                            else:
                                st.write( f"Version {i+1}:" )

                            trans_col, comments_col = st.columns(2)
                            with trans_col:
                                st.write( reflection_loop['graded_verse'] )
                            with comments_col:
                                if 'correction_summarization' in reflection_loop and \
                                        'summary' in reflection_loop['correction_summarization']:
                                    st.write( reflection_loop['correction_summarization']['summary'] )

                            st.divider()
                else:
                    st.write("No history")


            with verse_comments_tab:
                st.subheader("Comments applying to this verse")
                found_comment = False
                for i,comment in enumerate(get_comments_for_reference( st.session_state.comment_data,
                        st.session_state.book, st.session_state.chapter, st.session_state.verse )):
                    long_text = cached_to_range(comment['ids'],all_references)
                    truncation_length = 100
                    truncated_text = long_text[:truncation_length] + "..." if len(long_text) > \
                        truncation_length else long_text
                    changed_text = st.text_area( truncated_text, value=comment['comment'],
                        key=f"{i}-edit" )
                    save_col, delete_col = st.columns(2)
                    with save_col:
                        if st.button("Save", key=f"{i}-save"):
                            comment['comment'] = changed_text
                            save_comments(selected_translation, st.session_state.comment_data)
                            st.rerun()
                    with delete_col:
                        if st.button("Delete", key=f"{i}-delete"):
                            st.session_state.comment_data.remove(comment)
                            save_comments(selected_translation, st.session_state.comment_data)
                            st.rerun()
                    found_comment = True
                if not found_comment:
                    st.write("No comments found")


                add_comment_btn_text = "Add comment to this verse"
                # Create a button to run the JavaScript code
                if st.button(add_comment_btn_text):
                    if 'vrefs' in selected_verse:
                        st.session_state.selected_verses = selected_verse['vrefs']
                    else:
                        st.session_state.selected_verses = [selected_verse['vref']]
                    #javascript then switches to the Add Comments tab
                add_button_tab_switch(add_comment_btn_text, "Add Comments")


        # Add Comments Tab
        with add_comments_tab:
            st.header("Add Comments")
            st.subheader( "Select verses for comment" )

            if not st.session_state.selected_verses:
                long_text = "No selection for comment"
            else:
                long_text = cached_to_range(st.session_state.selected_verses,all_references)

            # Use the scrollable container
            st.markdown(f"""
                <div class="scrollable-container">
                    <pre>{long_text}</pre>
                </div>
                """, unsafe_allow_html=True)

            type_of_operation = st.radio( "What would you like to add or remove from the "
                "selection?", ["everything", "single", "range", "keyword search"],
                horizontal=True )


            scope = "book"
            if type_of_operation in ["single", "range"]:
                scope = st.radio( "What scope of selection?", ["book", "chapter", "verse"],
                horizontal=True )

            selection = ""
            if type_of_operation == "everything":
                selection = all_references
            elif type_of_operation == "single":
                single_selection = select_reference(scope, "single")
                selection = collect_references_within_range( single_selection, single_selection,
                    all_references )
            elif type_of_operation == "range":
                st.write( "Range start:")
                start_reference = select_reference(scope, "range-start")
                st.write( "Range end:")
                end_reference = select_reference(scope, "range-end")
                selection = collect_references_within_range( start_reference, end_reference,
                    all_references )
            elif type_of_operation == "keyword search":
                keyword = st.text_input( "Keyword" )
                selection = collect_references_with_keyword( keyword )
            add_col, remove_col = st.columns(2)
            with add_col:
                if st.button( "Add to selection" ):
                    for addition in selection:
                        if not addition in st.session_state.selected_verses:
                            st.session_state.selected_verses.append( addition )
                    sorted_references = []
                    for verse in all_references:
                        if verse in st.session_state.selected_verses:
                            sorted_references.append( verse )
                    st.session_state.selected_verses = sorted_references
                    st.rerun()
            with remove_col:
                if st.button( "Remove from selection" ):
                    for removal in selection:
                        if removal in st.session_state.selected_verses:
                            st.session_state.selected_verses.remove( removal )
                    st.rerun()




            if st.session_state.selected_verses:
                truncation_length = 20
                truncated_text = long_text[:truncation_length] + "..." if len( long_text ) > \
                    truncation_length else long_text
                st.subheader( f"Type comment to add to {truncated_text}")
                name = st.text_input( "Your Name" )
                comment_added = st.text_area( "Comment",
                    key=f"comment-{st.session_state.comment_count}", value="" )
                if st.button( "Add Comment to selected verses" ):

                    if name:

                        st.session_state.comment_data.append( {
                            "comment": comment_added,
                            "ids": st.session_state.selected_verses[:],
                            "name": name
                        })
                        save_comments(selected_translation,st.session_state.comment_data)

                        st.write( "Saved" )
                        st.session_state.comment_count += 1

                        st.rerun()
                    else:
                        st.error( "Please enter your name" )




def save_profiler_stats(profiler):
    """
    Save profiling results to a file.
    """
    # Generate a random integer for the filename
    random_int = random.randint(1000, 9999)
    filename = f"profiler_output_{random_int}.txt"

    # Write the profiling stats to a file
    with open(filename, "w", encoding="utf-8") as f:
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        ps.print_stats()
        f.write(s.getvalue())

    # Optionally, you can provide a link to download the file
    st.success(f"Profile results saved to: {filename}")
    # st.download_button(
    #     label="Download Profiling Results",
    #     data=open(filename, "rb").read(),
    #     file_name=filename,
    #     mime="text/plain"
    # )

PROFILEING = False

def profile_main():
    """
    Profile the main function.
    """
    if PROFILEING:
        try:
            profiler = cProfile.Profile()
            profiler.run("main()" )
            save_profiler_stats(profiler)
        except ValueError as e:
            if "profiling tool" in str(e):
                main()
            else:
                raise
    else:
        main()

# If this script is run directly, start the profiling
if __name__ == "__main__":
    profile_main()
