import os
import easy_draft
import gradio as gr
import json
from collections import OrderedDict
import time
import yaml

# Load the different bibles which are in the output.
loaded_outputs = [filename.rsplit('.', 1)[0] for filename in os.listdir('./output') if filename.endswith(".jsonl")]

with open( 'easy_draft.yaml', encoding='utf-8' ) as f:
    easy_draft_yaml = yaml.load(f, Loader=yaml.FullLoader)
ebible_dir = easy_draft_yaml['global_configs']['ebible_dir']
vrefs = easy_draft.load_file_to_list( os.path.join( ebible_dir, 'metadata', 'vref.txt' ) )

# Cache setup
class TranslationCache:
    def __init__(self, max_size=5):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.file_timestamps = {}

    def get(self, translation_name):
        file_path = f"output/{translation_name}.jsonl"
        current_timestamp = os.path.getmtime(file_path)

        # Check if the file is in cache and up to date
        if translation_name in self.cache and self.file_timestamps[translation_name] == current_timestamp:
            # Move accessed item to the end to mark it as recently used
            self.cache.move_to_end(translation_name)
            return self.cache[translation_name]

        # Load from file if not cached or outdated
        loaded_lines = list(map(json.loads, easy_draft.load_file_to_list(file_path)))
        loaded_lines = [{**loaded_line, 'vref': vrefs[i]} if loaded_line else None for i, loaded_line in enumerate(loaded_lines) ]
        loaded_lines = [line for line in loaded_lines if line]

        # Update the cache and timestamp
        self.cache[translation_name] = loaded_lines
        self.file_timestamps[translation_name] = current_timestamp
        self.cache.move_to_end(translation_name)

        # Ensure cache size limit
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

        return loaded_lines

translation_cache = TranslationCache()

def split_ref( reference ):
    last_space_index = reference.rindex(" ")
    book = reference[:last_space_index]
    chapter_num,verse_num = reference[last_space_index+1:].split(":")
    return book, chapter_num,verse_num


def load_translation(selected_translation):
    return translation_cache.get(selected_translation)

def get_books( selected_translation ):
    translation = load_translation( selected_translation )
    books = []
    for verse in translation:
        book,_,_ = split_ref( verse['vref'])
        if book not in books:
            books.append(book)
    return books

def get_chapters( selected_translation, index ):
    translation = load_translation( selected_translation )
    selected_book,_,_ = split_ref( translation[index]['vref'])

    chapters = []
    for verse in translation:
        last_space_index = verse['vref'].rindex(" ")
        other_book = verse['vref'][:last_space_index]
        if other_book == selected_book:
            chapter_num,_ = verse['vref'][last_space_index+1:].split(":")
            if chapter_num not in chapters:
                chapters.append(chapter_num)
    
    return chapters

def get_verses( selected_translation, index ):
    translation = load_translation( selected_translation )
    selected_book,selected_chapter_num,_ = split_ref( translation[index]['vref'] )

    verses = []
    for verse in translation:
        other_book,other_chapter,other_verse = split_ref( verse['vref'] )
        if other_book == selected_book and other_chapter == selected_chapter_num:
            verses.append( other_verse )
    return verses
def get_current_combined(index, selected_translation):
    translation = load_translation(selected_translation)

    if 0 <= index < len(translation):
        return f"{translation[index]['fresh_translation']['reference']}: {translation[index]['fresh_translation']['text']}"
    return "Invalid index"

def next_verse(index, selected_translation):
    index += 1
    verses = load_translation(selected_translation)
    if index >= len(verses):
        index = len(verses) - 1
    return get_current_combined(index, selected_translation), index

def previous_verse(index, selected_translation):
    index -= 1
    if index < 0:
        index = 0
    return get_current_combined(index, selected_translation), index


def selected_translation_dropdown_change( selected_translation, index ):
    translation = load_translation( selected_translation )
    if index >= len(translation):
        index = len(translation)-1
    books = get_books( selected_translation )
    chapters = get_chapters( selected_translation, index )
    verses = get_verses( selected_translation, index )
    text = get_current_combined( index, selected_translation )
    return index,books,chapters,verses,text

    #This isn't correct.  This is should only be able to return what is selected not what selection is available
    #that is done in a different way.

def book_change( selected_translation, selected_book, index ):
    translation = load_translation( selected_translation )
    current_book, current_chapter, current_verse = split_ref( translation[index]['vref'] )

    if current_book != selected_book:
        for i,verse in enumerate(translation):
            book,_,_ = split_ref( verse['vref'] )
            if book == selected_book:
                index = i
                break
    return index

# Interface components
with gr.Blocks() as demo:
    # Choose the translation
    selected_translation_dropdown = gr.Dropdown(
        choices=loaded_outputs,
        label="Choose a translation",
        value=loaded_outputs[0] if loaded_outputs else None
    )
    with gr.Tabs():
        with gr.Tab("Browse"):
            book = gr.Dropdown(choices=get_books(loaded_outputs[0]), label="Book")
            chapter = gr.Dropdown(choices=get_chapters(loaded_outputs[0],0), label="Chapter")
            verse = gr.Dropdown(choices=get_verses(loaded_outputs[0],0), label="Verse")
            current_index = gr.Number(value=0, label="Current Index", interactive=False, visible=False)
            current_combined = gr.Textbox(value=get_current_combined(0, loaded_outputs[0]), label="Current Verse and Reference", interactive=False)
            with gr.Row():
                prev_button = gr.Button("Previous")
                next_button = gr.Button("Next")

            selected_translation_dropdown.change(selected_translation_dropdown_change, inputs=[selected_translation_dropdown,current_index], outputs=[current_index,book,chapter,verse,current_combined])
            
            prev_button.click(previous_verse, inputs=[current_index, selected_translation_dropdown], outputs=[current_combined, current_index])
            next_button.click(next_verse, inputs=[current_index, selected_translation_dropdown], outputs=[current_combined, current_index])

        with gr.Tab("Add Comments"):
            gr.Textbox(value="Hello, World!", label="Add Comments")

# Launch the interface
demo.launch()
