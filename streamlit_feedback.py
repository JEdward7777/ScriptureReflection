import streamlit as st
import os
import json, yaml
import easy_draft

def split_ref( reference ):
    last_space_index = reference.rindex(" ")
    book_split = reference[:last_space_index]
    chapter_num,verse_num = reference[last_space_index+1:].split(":")
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

# Browse Tab
with tabs[0]:
    st.header("Browse Translation")

    # Load data for selected translation
    if selected_translation:
        translation_data = load_translation_data(selected_translation)

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


# Add Comments Tab
with tabs[1]:
    st.header("Add Comments")
    st.text("This feature is under development.")