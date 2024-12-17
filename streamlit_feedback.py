import streamlit as st
import os
import json, yaml
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


def get_text_for_reference(data, book, chapter, verse):
    """Fetches the text for a given reference."""
    for item in data:
        b, c, v = split_ref(item['vref'])
        if b == book and c == chapter and v == verse:
            return item['fresh_translation']['text']
    return "Text not found."

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


st.title("Translation Browser and Comment Tool")

# Translation Dropdown
selected_translation = st.selectbox("Select Translation", loaded_outputs)

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


if translation_data:
    all_references = collect_all_references()

    # Browse Tab
    with tabs[0]:
        st.header("Browse Translation")

        # Book, Chapter, Verse selectors
        unique_books = list(dict.fromkeys(split_ref(item['vref'])[0] for item in translation_data))


        book_col, chapter_col, verse_col = st.columns(3)


        with book_col:
            book = st.selectbox("Select Book", unique_books)

        # Use session state for chapter and verse
        chapter = st.session_state.chapter
        verse = st.session_state.verse

        chapter_before_dropdown = chapter
        verse_before_dropdown = verse

        with chapter_col:
            chapter = st.session_state.chapter = st.number_input("Select Chapter", min_value=1, value=chapter)
        with verse_col:
            verse = st.session_state.verse = st.number_input("Select Verse", min_value=1, value=verse)

        chapter_after_dropdown = chapter
        verse_after_dropdown = verse


        # Display current reference and text
        reference_text = get_text_for_reference(translation_data, book, chapter, verse)
        st.write(f"**{book} {chapter}:{verse}**")
        st.text_area("Current Text", reference_text, height=100, disabled=True)

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
                    st.session_state.verse += 1
                else:
                    next_chapter = st.session_state.chapter + 1
                    if any(split_ref(item['vref'])[1] == next_chapter for item in translation_data):
                        st.session_state.chapter += 1
                        st.session_state.verse = 1

        chapter_after_buttons = st.session_state.chapter
        verse_after_buttons = st.session_state.verse

        if chapter_before_dropdown != chapter_after_buttons: st.rerun()
        if verse_before_dropdown != verse_after_buttons: st.rerun()

    def select_reference( scope, key ):
        num_columns = 3 if scope == "verse" else 2 if scope == "chapter" else 1

        columns = st.columns(num_columns)

        result = ""

        with columns[0]:
            sel_book = st.selectbox("Select Book", unique_books, key=f"{key}-book")
            result = sel_book
        if num_columns >= 2:
            with columns[1]:
                sel_chapter = st.number_input("Select Chapter", min_value=1, key=f"{key}-chapter")
                result += f" {sel_chapter}"
        if num_columns == 3:
            with columns[2]:
                sel_verse = st.session_state.verse = st.number_input("Select Verse", min_value=1, key=f"{key}-verse")
                result += f":{sel_verse}"
        return result


    # Add Comments Tab
    with tabs[1]:
        st.header("Add Comment")
        if "selected_verses" not in st.session_state:
            st.session_state.selected_verses = []

        if not st.session_state.selected_verses:
            st.write( "No selection for comment" )
        else:
            st.write( f"Selected verses: {verse_parsing.to_range(st.session_state.selected_verses,all_references)}")

        type_of_operation = st.radio( f"What would you like to add or remove from the selection?", ["everything", "single", "range", "keyword search", "text reference"], horizontal=True )


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
            st.write( "This isn't implemented yet" )
            selection = ""
        elif type_of_operation == "text reference":
            st.write( "This isn't implemented yet" )
            selection = ""

        add_col, remove_col = st.columns(2)
        with add_col:
            if st.button( "Add" ):
                for addition in selection:
                    if not addition in st.session_state.selected_verses:
                        st.session_state.selected_verses.append( addition )
                st.rerun()
        with remove_col:
            if st.button( "Remove" ):
                for removal in selection:
                    if removal in st.session_state.selected_verses:
                        st.session_state.selected_verses.remove( removal )
                st.rerun()