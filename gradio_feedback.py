import os
import easy_draft
import gradio as gr
import json

# Load the different bibles which are in the output.
loaded_outputs = [filename.rsplit('.', 1)[0] for filename in os.listdir('./output') if filename.endswith(".jsonl")]


def load_translation( selected_translation ):
    """
    Loads a translation from its JSONL file in the output directory.
    Given a name of a translation, this function will load the corresponding
    JSONL file and return a list of its lines as Python dictionaries.
    """
    loaded_lines = list(map(json.loads, easy_draft.load_file_to_list(f"output/{selected_translation}.jsonl")))
    loaded_lines = [loaded_line for loaded_line in loaded_lines if loaded_line]
    return loaded_lines


def get_current_combined(index,selected_translation):
    translation = load_translation( selected_translation )


    if 0 <= index < len(translation):
        return f"{translation[index]['fresh_translation']['reference']}: {translation[index]['fresh_translation']['text']}"
    return "Invalid index"

def next_verse(index,selected_translation):
    index += 1
    verses = load_translation( selected_translation )
    if index >= len(verses):
        index = len(verses) - 1
    return get_current_combined(index,selected_translation), index

def previous_verse(index,selected_translation):
    index -= 1
    if index < 0:
        index = 0
    return get_current_combined(index,selected_translation), index

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
            current_index = gr.Number(value=0, label="Current Index", interactive=False, visible=False)
            current_combined = gr.Textbox(value=get_current_combined(0,loaded_outputs[0]), label="Current Verse and Reference", interactive=False)
            with gr.Row():
                prev_button = gr.Button("Previous")
                next_button = gr.Button("Next")
            
            prev_button.click(previous_verse, inputs=[current_index,selected_translation_dropdown], outputs=[current_combined, current_index])
            next_button.click(next_verse, inputs=[current_index,selected_translation_dropdown], outputs=[current_combined, current_index])

        with gr.Tab("Add Comments"):
            gr.Textbox(value="Hello, World!", label="Add Comments")

# Launch the interface
demo.launch()
