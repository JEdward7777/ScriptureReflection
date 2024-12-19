
import cProfile
#import profile as cProfile
import os
import pstats
import io
import random
from io import StringIO
import json, yaml
import streamlit as st
import easy_draft
import verse_parsing

def split_ref( reference ):
    if " " not in reference:
        return reference, None, None
    last_space_index = reference.rindex(" ")
    book_split = reference[:last_space_index]
    chapter_verse_str = reference[last_space_index+1:]
    if ":" not in chapter_verse_str:
        return book_split, int(chapter_verse_str), None
    chapter_num,verse_num = chapter_verse_str.split(":")
    return book_split, int(chapter_num), int(verse_num)

# Load available outputs
loaded_outputs = [filename.rsplit('.', 1)[0] for filename in os.listdir('./output') if filename.endswith(".jsonl")]

# Cache the loading of reference data
@st.cache_data
def load_reference_data():
    with open('easy_draft.yaml', encoding='utf-8') as f:
        easy_draft_yaml = yaml.load(f, Loader=yaml.FullLoader)
    ebible_dir = easy_draft_yaml['global_configs']['ebible_dir']
    return easy_draft.load_file_to_list(os.path.join(ebible_dir, 'metadata', 'vref.txt'))

#@st.cache_data
def cached_to_range(selected_verses, all_verses):
    return verse_parsing.to_range(selected_verses, all_verses)

@st.cache_data
def load_translation_data(selected_translation):
    """Loads the data for the selected translation."""
    vrefs = load_reference_data()
    filepath = f"./output/{selected_translation}.jsonl"
    with open(filepath, 'r', encoding='utf-8') as file:
        loaded_lines = [json.loads(line) for line in file]
    loaded_lines = [{**loaded_line, 'vref': vrefs[i]} if loaded_line else None for i, loaded_line in enumerate(loaded_lines)]
    loaded_lines = [line for line in loaded_lines if line]
    return loaded_lines


def load_comment_data(selected_translation):
    filepath = f"./output/comments/{selected_translation}.jsonl"
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            loaded_lines = [json.loads(line) for line in file]
        return loaded_lines
    except FileNotFoundError:
        return []

def save_comments(selected_translation,comment_data):
    filepath = f"./output/comments/{selected_translation}.jsonl"
    temp_filepath = f"./output/comments/{selected_translation}~.jsonl"
    if not os.path.exists("./output/comments"):
        os.makedirs("./output/comments")
    with open(temp_filepath, 'w', encoding='utf-8') as file:
        for this_comment in comment_data:
            file.write(json.dumps(this_comment) + "\n")
    os.replace(temp_filepath, filepath)


def get_text_for_reference(data, book, chapter, verse):
    """Fetches the text for a given reference."""
    for item in data:
        b, c, v = split_ref(item['vref'])
        if b == book and c == chapter and v == verse:
            return item['fresh_translation']['text']
    return "Text not found."

def get_comments_for_reference( comment_data, book, chapter, verse ):
    id = f"{book} {chapter}:{verse}"

    result = []
    for comment in comment_data:
        if id in comment['ids']:
            result.append(comment)

    return result

def reference_to_index(data,book,chapter,verse):
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
    st.title("Translation Comment Collector")

    # Translation Dropdown
    selected_translation = st.selectbox("Select Translation", loaded_outputs)

    if 'selected_translation' not in st.session_state or selected_translation != st.session_state.selected_translation:
        st.session_state.comment_data = load_comment_data(selected_translation)
        st.session_state.selected_verses = []
        st.session_state.selected_translation = selected_translation

    # Tabs
    tabs = st.tabs(["Browse", "Add Comments"])

    # Initialize session state variables
    if "chapter" not in st.session_state:
        st.session_state.chapter = 1
    if "verse" not in st.session_state:
        st.session_state.verse = 1


    if selected_translation:
        translation_data = load_translation_data(selected_translation)
    else:
        translation_data = []


    def collect_all_references():
        references = []
        for item in translation_data:
            references.append(item['vref'])
        return references

    def collect_references_within_range( start_reference, end_reference ):
        saw_start_book = False
        saw_start_chapter = False
        saw_start_verse = False

        saw_range_end = False

        sb, sc, sv = split_ref(start_reference)
        eb, ec, ev = split_ref(end_reference)

        references = []

        for item in translation_data:
            b, c, v = split_ref(item['vref'])

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
                references.append(item['vref'])

        return references


    def collect_references_with_keyword( keyword ):
        references = []
        for item in translation_data:
            if keyword in item['fresh_translation']['text']:
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

    if translation_data:

        # Book, Chapter, Verse selectors
        unique_books = list(dict.fromkeys(split_ref(item['vref'])[0] for item in translation_data))
        def select_reference( scope, key, init_chapter=None, init_verse=None ):
            num_columns = 3 if scope == "verse" else 2 if scope == "chapter" else 1

            columns = st.columns(num_columns)

            result = ""

            with columns[0]:
                sel_book = st.selectbox("Select Book", unique_books, key=f"{key}-book")
                result = sel_book
            if num_columns >= 2:
                with columns[1]:
                    max_chapter = 0
                    min_chapter = float('inf')
                    for item in translation_data:
                        b, c, _ = split_ref(item['vref'])
                        if b == sel_book:
                            max_chapter = max(max_chapter, c)
                            min_chapter = min(min_chapter, c)

                    if init_chapter is not None:
                        init_chapter = min( max( init_chapter, min_chapter ), max_chapter )
                        sel_chapter = st.number_input("Select Chapter", min_value=min_chapter, max_value=max_chapter, value=init_chapter, key=f"{key}-chapter")
                    else:
                        sel_chapter = st.number_input("Select Chapter", min_value=min_chapter, max_value=max_chapter, key=f"{key}-chapter")
                    result += f" {sel_chapter}"
            if num_columns == 3:
                with columns[2]:
                    max_verse = 0
                    min_verse = float('inf')
                    for item in translation_data:
                        b, c, v = split_ref(item['vref'])
                        if b == sel_book and c == sel_chapter:
                            max_verse = max(max_verse, v)
                            min_verse = min(min_verse, v)

                    if( min_verse != float('inf') ):
                        if init_verse is not None:
                            init_verse = min( max( init_verse, min_verse ), max_verse )
                            sel_verse = st.number_input("Select Verse", min_value=min_verse, max_value=max_verse, value=init_verse, key=f"{key}-verse")
                        else:
                            sel_verse = st.number_input("Select Verse", min_value=min_verse, max_value=max_verse, key=f"{key}-verse")
                        result += f":{sel_verse}"
                    else:
                        result += ":1"
            return result


        all_references = collect_all_references()

        # Browse Tab
        with tabs[0]:
            st.header("Browse Translation")


            # Use session state for chapter and verse
            chapter_before_dropdown = st.session_state.chapter
            verse_before_dropdown = st.session_state.verse


            book, st.session_state.chapter, st.session_state.verse = split_ref(select_reference( "verse", "browse", init_chapter=st.session_state.chapter, init_verse=st.session_state.verse ))


            # Display current reference and text
            reference_text = get_text_for_reference(translation_data, book, st.session_state.chapter, st.session_state.verse)
            st.write(f"**{book} {st.session_state.chapter}:{st.session_state.verse}**")
            #st.text_area("Current Text", reference_text, height=100, disabled=True)
            st.write( reference_text )

            # Next and Previous buttons
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Previous"):
                    if st.session_state.verse > 1:
                        st.session_state.verse -= 1
                    elif st.session_state.chapter > 1:
                        st.session_state.chapter -= 1
                        st.session_state.verse = max(split_ref(item['vref'])[2] for item in translation_data if split_ref(item['vref'])[0] == book and split_ref(item['vref'])[1] == st.session_state.chapter)
            with col2:
                if st.button("Next"):
                    max_verse = max(split_ref(item['vref'])[2] for item in translation_data if split_ref(item['vref'])[0] == book and split_ref(item['vref'])[1] == st.session_state.chapter)
                    if st.session_state.verse < max_verse:
                        st.session_state.verse = st.session_state.verse +1
                    else:
                        next_chapter = st.session_state.chapter + 1
                        if any(split_ref(item['vref'])[1] == next_chapter for item in translation_data):
                            st.session_state.chapter = next_chapter
                            st.session_state.verse = 1

            chapter_after_buttons = st.session_state.chapter
            verse_after_buttons = st.session_state.verse

            if chapter_before_dropdown != chapter_after_buttons:
                st.rerun()
            if verse_before_dropdown != verse_after_buttons:
                st.rerun()

            st.subheader("Comments applying to this verse")
            found_comment = False
            for i,comment in enumerate(get_comments_for_reference( st.session_state.comment_data, book, st.session_state.chapter, st.session_state.verse )):
                long_text = cached_to_range(comment['ids'],all_references)
                truncation_length = 100
                truncated_text = long_text[:truncation_length] + "..." if len(long_text) > truncation_length else long_text
                changed_text = st.text_area( truncated_text, value=comment['comment'], key=f"{i}-edit" )
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


        # Add Comments Tab
        with tabs[1]:
            st.header("Add Comments")
            st.subheader( "Select verses for comment" )
            if "selected_verses" not in st.session_state:
                st.session_state.selected_verses = []

            if not st.session_state.selected_verses:
                long_text = "No selection for comment"
            else:
                #st.write( f"Selected verses: {cached_to_range(st.session_state.selected_verses,all_references)}")
                long_text = cached_to_range(st.session_state.selected_verses,all_references)

            # Use the scrollable container
            st.markdown(f"""
                <div class="scrollable-container">
                    <pre>{long_text}</pre>
                </div>
                """, unsafe_allow_html=True)

            type_of_operation = st.radio( "What would you like to add or remove from the selection?", ["everything", "single", "range", "keyword search"], horizontal=True )


            scope = "book"
            if type_of_operation in ["single", "range"]:
                scope = st.radio( "What scope of selection?", ["book", "chapter", "verse"], horizontal=True )

            selection = ""
            if type_of_operation == "everything":
                selection = all_references
            elif type_of_operation == "single":
                single_selection = select_reference(scope, "single")
                selection = collect_references_within_range( single_selection, single_selection )
            elif type_of_operation == "range":
                st.write( "Range start:")
                start_reference = select_reference(scope, "range-start")
                st.write( "Range end:")
                end_reference = select_reference(scope, "range-end")
                selection = collect_references_within_range( start_reference, end_reference )
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
                truncated_text = long_text[:truncation_length] + "..." if len( long_text ) > truncation_length else long_text
                st.subheader( f"Type comment to add to {truncated_text}")
                comment_added = st.text_area( "Comment", key="comment" )
                if st.button( "Add Comment to selected verses" ):

                    st.session_state.comment_data.append( {
                        "comment": comment_added,
                        "ids": st.session_state.selected_verses[:]
                    })
                    save_comments(selected_translation,st.session_state.comment_data)

                    st.rerun()


def save_profiler_stats(profiler):
    # Generate a random integer for the filename
    random_int = random.randint(1000, 9999)
    filename = f"profiler_output_{random_int}.txt"
    
    # Write the profiling stats to a file
    with open(filename, "w") as f:
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