"""
This is a POC for a Streamlit app to allow users to provide feedback on the quality of a
translation. But it is evolving into more, such as editing the translation as well.
"""

#disable C0321:multiple-statements in pylint for the entire module.
# pylint: disable=C0321

#disable C0302:too-many-lines in pylint for the entire module.
# pylint: disable=C0302

import cProfile
#import profile as cProfile
import os
import pstats
import io
import random
import itertools
import json
import math
import time
import yaml
import streamlit as st
from streamlit.components.v1 import html
import utils
import verse_parsing
import grade_reflect_loop
import JLDiff

profiling_array = []

def run_diff( string_a, string_b ):
    diff_trace = JLDiff.compute_diff( string_a, string_b, talk=False )
    #now convert diff_trace to a string by calling printDiffs and passing
    #a buffer that .write can be called on that will create a string.
    diff_string = io.StringIO()
    JLDiff.printDiffs( diff_trace, diff_string )
    diff_string = diff_string.getvalue()
    return diff_string


def reset_profile():
    """Clears the profiling array"""
    profiling_array.clear()

def checkpoint( description ):
    """Adds a checkpoint to the profiling array"""
    now = time.time()
    last_time = profiling_array[-1][-1] if len(profiling_array) > 0 else now
    duration = now - last_time
    profiling_array.append( (description, duration, now ) )

def save_out_profiling( filename ):
    """Saves the profiling array to a file"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Description,Duration,Time\n")
        for description, duration, post_time in profiling_array:
            f.write(f"{description},{duration},{post_time}\n")


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
def load_translation_data(selected_translation, reference_key, override_key):
    """Loads the data for the selected translation."""
    #vrefs = load_reference_data()
    vrefs = None
    filepath = f"./output/{selected_translation}.jsonl"



    with open(filepath, 'r', encoding='utf-8') as file:
        loaded_lines = [json.loads(line) for line in file]

    filtered_translation_data = []
    indexed_translation_data = {}
    all_references = []
    all_references__dict = {}
    for i, loaded_line in enumerate(loaded_lines):
        if loaded_line:

            vref = utils.look_up_key(loaded_line, reference_key)
            if utils.look_up_key(loaded_line, reference_key) is None:
                if vrefs is None: vrefs = load_reference_data()
                vref = vrefs[i]
                utils.set_key( loaded_line, reference_key, vref )

            b,c,v = split_ref(vref)
            #if the verse is a range, v comes back as a string like "3-5"
            if isinstance(v, str):
                start_verse, end_verse = v.split("-")
                for verse in range(int(start_verse), int(end_verse)+1):
                    utils.set_key( indexed_translation_data, [b,c,verse], loaded_line )
                    range_ref = f"{b} {c}:{verse}"
                    if range_ref not in all_references__dict:
                        all_references.append( f"{b} {c}:{verse}" )
                        all_references__dict[range_ref] = True
            else:
                utils.set_key( indexed_translation_data, [b,c,v], loaded_line )
                all_references.append( vref )
                all_references__dict[vref] = True

            if override_key and utils.look_up_key(loaded_line, override_key):
                #if the last one was overridden, (i.e. verse range)
                #Then pop the last one out of the filtered list.
                filtered_translation_data.pop()


            filtered_translation_data.append(loaded_line)


    return { "full": loaded_lines,
        "indexed": indexed_translation_data, 
        "filtered": filtered_translation_data,
        "all_references": all_references,
    }

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

def touch_verse( verse_id, indexed_translation_data ):
    """Modifies the translation file so that the background processes which change things will know
    a new comment has been added etc."""

    b,c,v = split_ref(verse_id)
    if b in indexed_translation_data:
        selected_book = indexed_translation_data[b]
        if c in selected_book:
            selected_chapter = selected_book[c]
            if v in selected_chapter:
                selected_verse = selected_chapter[v]
                selected_verse['comment_mod_loop_count'] = len( selected_verse.get(
                    'reflection_loops', [] ) )




def save_comments(selected_translation,comment_data,comment_changed_or_removed,
        translation_data_and_indexed_translation_data):
    """Saves the comment data for a selected translation"""
    filepath = f"./output/comments/{selected_translation}.jsonl"
    temp_filepath = f"./output/comments/{selected_translation}~.jsonl"
    if not os.path.exists("./output/comments"):
        os.makedirs("./output/comments")
    with open(temp_filepath, 'w', encoding='utf-8') as file:
        for this_comment in comment_data:
            file.write(json.dumps(this_comment) + "\n")
    os.replace(temp_filepath, filepath)

    #now touch all the verses in the translation which received a comment.
    for verse_id in comment_changed_or_removed['ids']:
        touch_verse( verse_id, translation_data_and_indexed_translation_data['indexed'] )

    #save the translation back out because the touch marks are in that file.
    save_translation_data( selected_translation,
        translation_data_and_indexed_translation_data['full'] )

def get_verse_for_reference( indexed_data, book, chapter, verse ):
    """Fetches the verse object for a given reference"""

    #if this is a range, just take the last one
    if isinstance(verse, str):
        verse = int(verse.split("-")[-1])

    if book in indexed_data and chapter in indexed_data[book] and verse in \
            indexed_data[book][chapter]:
        return indexed_data[book][chapter][verse]

    return None

def get_comments_for_reference( comment_data, book, chapter, verse ):
    """Gets the comments for a specific reference"""
    #TO DO: This needs to be refactored to be more efficient
    #by indexing the comments when they are loaded.
    vref = f"{book} {chapter}:{verse}"

    result = []
    for comment in comment_data:
        if vref in comment['ids']:
            result.append(comment)

    return result


def get_sorted_verses( translation_data, reference_key ):
    """Returns the next verse as sorted by grades"""
    fake_config_for_grade_reflect_loop = {
        'reference_key': reference_key,
        'grades_per_reflection_loop': float('inf'),
    }

    def get_grade( verse ):
        grade = grade_reflect_loop.compute_verse_grade( verse, fake_config_for_grade_reflect_loop )
        if grade is not None:
            return grade
        return 0

    sorted_verses = sorted( translation_data['filtered'], key=get_grade )

    return sorted_verses



def get_next_by_grade( translation_data, selected_verse, reference_key ):
    """Returns the next verse as sorted by grades"""

    verse_to_return = selected_verse

    sorted_verses = get_sorted_verses( translation_data, reference_key )

    if sorted_verses:
        current_index = sorted_verses.index( selected_verse )
        next_index = current_index + 1 if current_index < len(sorted_verses) - 1 else current_index
        verse_to_return = sorted_verses[next_index]

    return split_ref(utils.look_up_key( verse_to_return, reference_key ))

def get_previous_by_grade( translation_data, selected_verse, reference_key ):
    """Returns the previous verse to be graded"""

    verse_to_return = selected_verse

    sorted_verses = get_sorted_verses( translation_data, reference_key )

    if sorted_verses:
        current_index = sorted_verses.index( selected_verse )
        previous_index = current_index - 1 if current_index > 0 else current_index
        verse_to_return = sorted_verses[previous_index]

    return split_ref(utils.look_up_key( verse_to_return, reference_key ))

def main():
    """Main function for the Streamlit app."""
    reset_profile()
    checkpoint( "start" )


    st.title("Scripture Reflector")

    # Translation Dropdown
    selected_translation = st.selectbox("Select Translation", loaded_outputs)

    streamlit_reflector_yaml = utils.load_yaml_configuration( 'streamlit_reflector.yaml' )
    config = streamlit_reflector_yaml.get( 'configs', utils.GetStub() ). \
        get( selected_translation, utils.GetStub() )

    reference_key           = config.get( 'reference_key', ['vref'] )
    translation_key         = config.get( 'translation_key', ['fresh_translation','text'] )
    translation_comment_key = config.get( 'translation_comment_key', ['translation_notes'] )
    source_key              = config.get( 'source_key', ['source'] )
    override_key            = config.get( 'override_key', \
        ['forming_verse_range_with_previous_verse'] )


    checkpoint( "about to load translation" )

    if selected_translation:
        translation_data_and_indexed_translation_data = load_translation_data(selected_translation,
            reference_key, override_key)
    else:
        translation_data_and_indexed_translation_data = {}

    checkpoint( "loaded translation" )



    if 'selected_translation' not in st.session_state or selected_translation != \
            st.session_state.selected_translation:
        st.session_state.comment_data = load_comment_data(selected_translation)
        st.session_state.selected_verses = []
        st.session_state.selected_translation = selected_translation

    checkpoint( "managed session state" )

    # Tabs
    browse_chapter_tab, browse_verse_tab, sorter_tab, add_comments_tab = \
        st.tabs(["Browse Chapter", "Browse Verse", "Sorter", "Add Comments"])

    # Initialize session state variables
    if "book" not in st.session_state:
        st.session_state.book = "GEN"
    if "chapter" not in st.session_state:
        st.session_state.chapter = 1
    if "verse" not in st.session_state:
        st.session_state.verse = 1


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
        for item in translation_data_and_indexed_translation_data['filtered']:
            if not item:
                continue
            translation = utils.look_up_key( item, translation_key )
            if keyword.lower() in translation.lower():
                references.append(utils.look_up_key( item, reference_key ))
        return references

    # Add custom CSS for scrolling and other things.
    st.markdown("""
        <style>
        .scrollable-container {
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid #ccc;
            padding: 10px;
            background-color: #f9f9f9;
        }
        /* JLDiff coloring */
        .new{color:darkgreen;background-color:lightyellow}
        .old{color:red;background-color:pink}
        </style>
        """, unsafe_allow_html=True)

    if 'filtered' in translation_data_and_indexed_translation_data and \
            translation_data_and_indexed_translation_data['filtered']:

        checkpoint( "Finding unique_books")

        # Book, Chapter, Verse selectors
        unique_books = list(translation_data_and_indexed_translation_data['indexed'].keys())
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
                    if sel_book in translation_data_and_indexed_translation_data['indexed']:
                        chapters = translation_data_and_indexed_translation_data['indexed'] \
                            [sel_book].keys()
                        max_chapter = max(chapters)
                        min_chapter = min(chapters)

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

                    if sel_book in translation_data_and_indexed_translation_data['indexed']:
                        if sel_chapter in translation_data_and_indexed_translation_data['indexed'] \
                                [sel_book]:
                            verses = translation_data_and_indexed_translation_data['indexed'] \
                                [sel_book][sel_chapter].keys()
                            max_verse = get_max_verse(verses)
                            min_verse = get_min_verse(verses)

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


        checkpoint( "Finding all references" )

        all_references = translation_data_and_indexed_translation_data['all_references']


        if "selected_verses" not in st.session_state:
            st.session_state.selected_verses = []

        if "comment_count" not in st.session_state:
            st.session_state.comment_count = 0


        # Browse chapter Tab
        with browse_chapter_tab:

            checkpoint( "chapter tab: Starting browse tab" )

            st.header("Browse Translation by Chapter")
            st.write("Select a book and chapter to view the verses in that chapter.")

            book_before_dropdown = st.session_state.book
            chapter_before_dropdown = st.session_state.chapter

            st.session_state.book, st.session_state.chapter, _ = split_ref(select_reference(
                "chapter", "browse-chapter", init_book=st.session_state.book,
                init_chapter=st.session_state.chapter ))

            checkpoint( "chapter tab: got selected chapter" )


            max_chapter = None
            min_chapter = None

            if st.session_state.book in translation_data_and_indexed_translation_data['indexed']:
                chapters = translation_data_and_indexed_translation_data['indexed'] \
                    [st.session_state.book].keys()
                max_chapter = max(chapters)
                min_chapter = min(chapters)

                if st.session_state.chapter in chapters:
                    last_item = None
                    for item in translation_data_and_indexed_translation_data['indexed'] \
                            [st.session_state.book][st.session_state.chapter].values():
                        if item is not last_item:
                            vref = utils.look_up_key( item, reference_key )
                            button_text = f"{vref}"
                            if st.button( button_text ):
                                _,_,st.session_state.verse = split_ref(vref)

                            trans_col, source_col = st.columns(2)
                            with trans_col:
                                st.write( utils.look_up_key( item, translation_key ) )
                            with source_col:
                                st.write( utils.look_up_key( item, source_key ) )

                        last_item = item

            checkpoint( "chapter tab: Found items in current chapter" )

            # Next and Previous buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("<- Previous", key="chapter-prev"):
                    if st.session_state.chapter > min_chapter:
                        st.session_state.chapter -= 1
            with col2:
                pass
            with col3:
                if st.button("Next ->", key="chapter-next"):
                    if st.session_state.chapter < max_chapter:
                        st.session_state.chapter += 1

            checkpoint( "chapter tab: Made prev next buttons in chapter" )


            #put the button to tab connections at the bottom because they produce height.
            if st.session_state.book in translation_data_and_indexed_translation_data['indexed']:
                if st.session_state.chapter in translation_data_and_indexed_translation_data \
                        ['indexed'][st.session_state.book]:
                    last_item = None
                    for item in translation_data_and_indexed_translation_data['indexed'] \
                            [st.session_state.book][st.session_state.chapter].values():
                        if item is not last_item:
                            vref = utils.look_up_key( item, reference_key )
                            button_text = f"{vref}"
                            add_button_tab_switch( button_text, "Browse Verse" )
                        last_item = item

            checkpoint( "chapter tab: Added the switch button macros" )

            if st.session_state.book != book_before_dropdown or st.session_state.chapter != \
                    chapter_before_dropdown:
                st.rerun()

        selected_verse = None
        # Browse verse Tab
        with browse_verse_tab:
            checkpoint( "verse tab: Starting browse tab" )

            st.header("Browse Translation by Verse")


            # Use session state for chapter and verse
            book_before_dropdown = st.session_state.book
            chapter_before_dropdown = st.session_state.chapter
            verse_before_dropdown = st.session_state.verse


            st.session_state.book, st.session_state.chapter, st.session_state.verse = split_ref(
                select_reference( "verse", "browse-verse", init_book=st.session_state.book,
                init_chapter=st.session_state.chapter, init_verse=st.session_state.verse ))


            checkpoint( "verse tab: Ran verse selectors" )

            selected_verse = get_verse_for_reference(
                translation_data_and_indexed_translation_data['indexed'],
                st.session_state.book, st.session_state.chapter, st.session_state.verse )


            checkpoint( "verse tab: Looked up active verse" )

            current_verse_grade = None
            if selected_verse is not None:
                if 'reflection_is_finalized' in selected_verse and \
                    selected_verse['reflection_is_finalized']:
                    st.write( f"**{utils.look_up_key( selected_verse, reference_key )}** "
                        f"_(Grade {selected_verse['reflection_finalized_grade']:.1f})_" )
                    current_verse_grade = selected_verse['reflection_finalized_grade']
                elif 'reflection_loops' in selected_verse and \
                        len(reflection_loops := selected_verse['reflection_loops']) > 0 and \
                        'average_grade' in (last_reflection_loop := reflection_loops[-1]) and \
                        'graded_verse' not in last_reflection_loop:
                    st.write( f"**{utils.look_up_key( selected_verse, reference_key )}** "
                        f"_(Grade {last_reflection_loop['average_grade']:.1f})_" )
                    current_verse_grade = last_reflection_loop['average_grade']
                else:
                    st.write(f"**{utils.look_up_key( selected_verse, reference_key )}**")
            else:
                st.write( "No selected verse" )

            checkpoint( "verse tab: wrote verse header" )

            # Display current reference and text
            reference_text = utils.look_up_key( selected_verse, translation_key, "" )

            edited_verse = st.text_area( "**Translation:**", value=reference_text,
                key="verse-edit" )
            if edited_verse != reference_text:
                edit_verse( selected_verse, reference_text, edited_verse, translation_key,
                    translation_comment_key )
                save_translation_data( selected_translation,
                    translation_data_and_indexed_translation_data['full'] )
                st.rerun()

            checkpoint( "verse tab: showed verse to be edited" )

            #display the source text.
            source_text = utils.look_up_key( selected_verse, source_key )
            st.write( "**Source Text:**")
            st.write( source_text)


            checkpoint( "verse tab: about to show suggested corrections" )

            show_diffs = False

            #see if we have a summarized comment to display:
            if selected_verse and ('reflection_loops' in selected_verse) and \
                    len(reflection_loops := selected_verse['reflection_loops']) > 0:
                last_reflection_loop = reflection_loops[-1]
                #if the verse is finalized, then the grade in the last reflection loop
                #probably isn't ours because the best verse was picked out.
                if 'reflection_is_finalized' in selected_verse and \
                        selected_verse['reflection_is_finalized']:
                    st.write( "**Suggested Corrections:**")
                    st.write( "_No corrections.  Verse replaced with best graded verse from "
                        "history._")

                #if graded_verse is stashed in the last_reflection_loop
                #Then the grade is not for the current translation.
                elif 'graded_verse' not in last_reflection_loop:
                    if 'correction_summarization' in last_reflection_loop and \
                            'summary' in last_reflection_loop['correction_summarization']:
                        st.write( "**Suggested Correction:**" )
                        st.write( last_reflection_loop['correction_summarization']['summary'] )

                    #otherwise see if we can just write out the grade comments.
                    elif 'grades' in last_reflection_loop:
                        st.write( "**Suggested Corrections:**" )
                        for i,grade in enumerate(last_reflection_loop['grades']):
                            st.write( f"**Review {i+1}** "
                                f"_(Grade {grade['grade']})_: {grade['comment']}" )

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    reviewed = utils.look_up_key( selected_verse, ['human_reviewed'], False )
                    changed_reviewed = st.checkbox( "Reviewed", value=reviewed,
                        key='human_reviewed' )
                    if changed_reviewed != reviewed:
                        selected_verse['human_reviewed'] = changed_reviewed
                        save_translation_data( selected_translation,
                            translation_data_and_indexed_translation_data['full'] )
                        st.toast( "Saved" )
                        st.rerun()

                with col2:
                    ai_halted = selected_verse.get("ai_halted", False )
                    ai_haulted_input = st.checkbox( "Halt AI for this", value=ai_halted, key='ai_halted' )
                    if ai_haulted_input != ai_halted:
                        selected_verse['ai_halted'] = ai_haulted_input
                        save_translation_data( selected_translation,
                            translation_data_and_indexed_translation_data['full'] )
                        st.toast( "Saved" )
                        st.rerun()

                with col3:
                    grade_only = selected_verse.get("grade_only", False )
                    grade_only_input = st.checkbox( "AI only grades", value=grade_only, key="grade_only" )
                    if grade_only_input != grade_only:
                        selected_verse['grade_only'] = grade_only_input
                        save_translation_data( selected_translation,
                            translation_data_and_indexed_translation_data['full'] )
                        st.toast( "Saved" )
                        st.rerun()

                with col4:
                    show_diffs = st.checkbox( "Show Diffs", value=False, key='show_diffs' )

            checkpoint( "verse tab: showed suggested corrections" )

            # Next and Previous buttons
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if st.button("<- Previous"):
                    if st.session_state.verse > 1:
                        st.session_state.verse -= 1
                    elif st.session_state.chapter > 1 and (st.session_state.chapter - 1) in \
                            translation_data_and_indexed_translation_data['indexed'] \
                            [st.session_state.book]:
                        st.session_state.chapter -= 1
                        st.session_state.verse = get_max_verse(
                            translation_data_and_indexed_translation_data['indexed'] \
                                [st.session_state.book][st.session_state.chapter].keys())
            with col2:
                if st.button("Next ->"):
                    max_verse = get_max_verse(translation_data_and_indexed_translation_data \
                        ['indexed'][st.session_state.book][st.session_state.chapter].keys())
                    if st.session_state.verse < max_verse:
                        st.session_state.verse = st.session_state.verse +1
                    else:
                        next_chapter = st.session_state.chapter + 1
                        if next_chapter in translation_data_and_indexed_translation_data \
                                ['indexed'][st.session_state.book]:
                            st.session_state.chapter = next_chapter
                            st.session_state.verse = 1

            with col3:
                if st.button( "<- Lower grade" ):
                    st.session_state.book, st.session_state.chapter, st.session_state.verse = \
                        get_previous_by_grade( translation_data_and_indexed_translation_data,
                            selected_verse, reference_key )
            with col4:
                if st.button( "Higher grade ->" ):
                    st.session_state.book, st.session_state.chapter, st.session_state.verse = \
                        get_next_by_grade( translation_data_and_indexed_translation_data,
                            selected_verse, reference_key )

            if show_diffs:
                #Here we will look at the last version before the active verse and run JLDiff
                #to see the differences and display that.
                for reflection_loop in reversed(selected_verse.get( 'reflection_loops', [] )):
                    if 'graded_verse' in reflection_loop:
                        previous_verse = reflection_loop['graded_verse']
                        break
                else:
                    previous_verse = None

                if previous_verse:
                    diff_string = run_diff( previous_verse, reference_text )
                    #now we need to create an StreamLit component which allows viewing html
                    #so that the colors show up.
                    #This is a security problem if someone wants to start putting
                    #in verses with javascript in them.
                    st.markdown( "**Diff:** " + diff_string, unsafe_allow_html=True )



            checkpoint( "verse tab: wrote next and previous buttons" )

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
                checkpoint( "verse tab: history tab: started" )
                st.header("Verse History")

                found_history = False
                reflection_loops = selected_verse.get( 'reflection_loops', [] )
                if selected_verse and reflection_loops:
                    grade_over_history = []

                    #iterate the reflection loops in reverse.
                    for i,reflection_loop in reversed(list(enumerate(reflection_loops))):
                        if 'graded_verse' in reflection_loop:

                            trans_col, comments_col = st.columns(2)
                            with trans_col:
                                found_history = True
                                if 'average_grade' in reflection_loop:
                                    st.write( f"**Version {i+1}**: "
                                        f"_(Grade {reflection_loop['average_grade']:.1f})_" )

                                    grade_over_history.append( reflection_loop['average_grade'] )
                                else:
                                    st.write( f"Version {i+1}:" )


                                st.write( reflection_loop['graded_verse'] )

                                if show_diffs and i > 0:
                                    #see if we can find a previous verse.
                                    diff_string = run_diff( 
                                        reflection_loops[i-1].get('graded_verse',''), 
                                        reflection_loop      .get('graded_verse','') )
                                    st.markdown( "**Diff:** " + diff_string, unsafe_allow_html=True )
                            with comments_col:
                                #add a summarization tab and a grade comments tab.
                                summarization_tab, grade_comments_tab = st.tabs(["Summarization", "Grade Comments"])

                                with summarization_tab:
                                    if 'correction_summarization' in reflection_loop and \
                                            'summary' in reflection_loop['correction_summarization']:
                                        st.write( reflection_loop['correction_summarization']
                                            ['summary'] )
                                with grade_comments_tab:
                                    for grade_i,grade in enumerate(reflection_loop.get("grades",[])):
                                        st.write( f"**Review {grade_i+1}** "
                                            f"_(Grade {grade['grade']})_: {grade['comment']}" )


                            st.divider()

                    checkpoint( "verse tab: history tab: showed history" )

                    if grade_over_history:
                        #The starting [None] makes the first used x index 1 like the versions.
                        st.line_chart( itertools.chain([None],reversed(grade_over_history), \
                            [current_verse_grade]), x_label="Version", y_label="Grade" )

                        checkpoint( "verse tab: history tab: showed chart" )

                if not found_history:
                    st.write("No history")


            with verse_comments_tab:
                checkpoint( "verse tab: comments tab: started" )

                st.subheader("Comments applying to this verse")
                found_comment = False
                for i,comment in enumerate(get_comments_for_reference(
                        st.session_state.comment_data, st.session_state.book,
                        st.session_state.chapter, st.session_state.verse )):
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
                            save_comments(selected_translation, st.session_state.comment_data,
                                comment,translation_data_and_indexed_translation_data)
                            st.rerun()
                    with delete_col:
                        if st.button("Delete", key=f"{i}-delete"):
                            st.session_state.comment_data.remove(comment)
                            save_comments(selected_translation, st.session_state.comment_data,
                                comment,translation_data_and_indexed_translation_data)
                            st.rerun()
                    found_comment = True
                if not found_comment:
                    st.write("No comments found")

                checkpoint( "verse tab: comments tab: showed comments" )


                add_comment_btn_text = "Add comment to this verse"
                # Create a button to run the JavaScript code
                if st.button(add_comment_btn_text):
                    if 'vrefs' in selected_verse:
                        st.session_state.selected_verses = selected_verse['vrefs']
                    else:
                        vref = utils.look_up_key( selected_verse, reference_key )
                        b,c,v = split_ref(vref)
                        #if the verse is a range, v comes back as a string like "3-5"
                        if isinstance(v, str):
                            start_verse,end_verse = v.split("-")
                            st.session_state.selected_verses = [
                                f"{b} {c}:{r_v}" for r_v in
                                range(int(start_verse),int(end_verse)+1)]
                        else:
                            st.session_state.selected_verses = [vref]

                    #javascript then switches to the Add Comments tab
                add_button_tab_switch(add_comment_btn_text, "Add Comments")

                checkpoint( "verse tab: comments tab: wrote add comment button" )

        with sorter_tab:
            checkpoint( "sorter tab: started" )

            st.header( "Verse Sorter" )

            #pylint: disable=C0103
            BY_GRADE = "By Grade"
            BY_IMPROVEMENT = "By Grade Improvement"

            #add sort mode and if human reviewed in one row.
            sort_mode = st.radio( "Sort Mode", [BY_GRADE, BY_IMPROVEMENT], index=None )
            include_human_reviewed = st.checkbox( "Include Reviewed" )
            if sort_mode is None and "sort_mode" in st.session_state:
                sort_mode = st.session_state.sort_mode
                include_human_reviewed = st.session_state.include_human_reviewed
            st.session_state.sort_mode = sort_mode
            st.session_state.include_human_reviewed = include_human_reviewed

            st.write( f"Sortmode {sort_mode} include human reviewed {include_human_reviewed}" )

            fake_config_for_grade_reflect_loop = {
                'reference_key': reference_key,
                'grades_per_reflection_loop': float('inf'),
            }

            def get_grade( verse ):
                return grade_reflect_loop.compute_verse_grade( verse,
                    fake_config_for_grade_reflect_loop )

            def get_grade_improvement( verse ):
                final_grade = get_grade( verse )
                if final_grade is None:
                    return None

                #now see if we can find the earliest grade.
                if 'reflection_loops' in verse:
                    reflection_loops = verse['reflection_loops']
                    if reflection_loops:
                        first_reflection_loop = reflection_loops[0]
                        first_grade = grade_reflect_loop.compute_grade_for_reflection_loop(
                            first_reflection_loop, fake_config_for_grade_reflect_loop )

                        if first_grade is not None:
                            return final_grade-first_grade
                return None


            selected_sorter = get_grade if sort_mode == BY_GRADE else get_grade_improvement

            def should_include_verse( verse ):
                if not include_human_reviewed:
                    human_reviewed = utils.look_up_key( verse, ['human_reviewed'], False )
                    if human_reviewed:
                        return False
                if selected_sorter( verse ) is None:
                    return False
                return True

            sorted_by_feature = sorted( (x for x in translation_data_and_indexed_translation_data \
                    ['filtered'] if should_include_verse(x)), key=selected_sorter, reverse=False \
                    if sort_mode == BY_GRADE else True  )


            checkpoint( "sorter tab: sorted" )

            if not sorted_by_feature:
                st.write( "No graded verses." )
            else:

                verses_per_page = 10
                page = st.session_state.page if 'page' in st.session_state else 1
                num_pages = math.ceil(len(sorted_by_feature) / verses_per_page)

                metric_per_page = [selected_sorter(sorted_by_feature[i * verses_per_page]) for i \
                    in range(num_pages)]
                st.line_chart(data=metric_per_page, x_label="page", y_label="grade" if \
                    sort_mode == BY_GRADE else "improvement" )

                checkpoint( "sorter tab: showed chart" )


                # Create a slider to navigate through pages
                page = st.slider("Go to page", 1, num_pages, key="page_slider")

                checkpoint( "sorter tab: slider" )

                # Display current page and total pages
                st.write(f"Page {page} of {num_pages}")

                start_index = (page - 1) * verses_per_page
                end_index = start_index + verses_per_page

                sorted_by_feature_page = sorted_by_feature[start_index:end_index]

                for i,verse in enumerate(sorted_by_feature_page):
                    reference = utils.look_up_key( verse, reference_key )
                    translation = utils.look_up_key( verse, translation_key )
                    grade = get_grade( verse )
                    grade_improvement = get_grade_improvement( verse )

                    #st.write( f"**{reference}**: _(Grade {grade:.1f})_" )
                    with st.container( border=verse is selected_verse ):
                        cols = st.columns(4)
                        with cols[0]:
                            if st.button( f"Ref: {reference}", key=f"sort-verse-{i}" ):
                                vref = utils.look_up_key( verse, reference_key )
                                st.session_state.book,st.session_state.chapter,v = \
                                    split_ref(vref)
                                if isinstance(v, str):
                                    start_verse = v.split("-")[0]
                                    st.session_state.verse = int(start_verse)
                                else:
                                    st.session_state.verse = v
                                st.rerun()
                        with cols[1]:
                            st.write( f"_Grade: {grade:.1f}_" )
                        with cols[2]:
                            st.write( f"_Improvement: {grade_improvement:.1f}_")
                        with cols[3]:
                            human_reviewed = utils.look_up_key( verse, ['human_reviewed'], False )
                            if human_reviewed:
                                st.write( "_Reviewed_" )

                        st.write( translation )

                    st.divider()

                checkpoint( "sorter tab: showed verses" )

                # Now tag on the tab switching feature, but we do it in a secondary loop because
                # it adds height.
                for i,verse in enumerate(sorted_by_feature_page):
                    reference = utils.look_up_key( verse, reference_key )
                    add_button_tab_switch( f"Ref: {reference}", "Browse Verse" )

                checkpoint( "sorter tab: add_button_tab_switch" )



        # Add Comments Tab
        with add_comments_tab:
            checkpoint( "add comments tab: started" )

            st.header("Add Comments")
            st.subheader( "Select verses for comment" )

            if not st.session_state.selected_verses:
                long_text = "No selection for comment"
            else:
                long_text = cached_to_range(st.session_state.selected_verses,all_references)

            checkpoint( "add comments tab: wrote long text" )

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

            checkpoint( "add comments tab: selected scope" )

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


            checkpoint( "add comments tab: wrote selection" )

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

                        new_comment_object = {
                            "comment": comment_added,
                            "ids": st.session_state.selected_verses[:],
                            "name": name
                        }
                        st.session_state.comment_data.append( new_comment_object )
                        save_comments(selected_translation,st.session_state.comment_data,
                            new_comment_object,translation_data_and_indexed_translation_data)

                        st.write( "Saved" )
                        st.session_state.comment_count += 1

                        st.rerun()
                    else:
                        st.error( "Please enter your name" )

                checkpoint( "add comments tab: made add comment" )




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
PROFILEING2 = False

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

    if PROFILEING2:
        save_out_profiling( "streamlit_reflector_profiling.csv" )

# If this script is run directly, start the profiling
if __name__ == "__main__":
    profile_main()
