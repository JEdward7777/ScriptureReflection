import os
import gradio as gr

# Load the different bibles which are in the output.
loaded_outputs = [filename.rsplit('.', 1)[0] for filename in os.listdir('./output') if filename.endswith(".jsonl")]

def get_verses():
    return [
        "In the beginning God created the heavens and the earth.",
        "And God said, 'Let there be light,' and there was light.",
        "God saw that the light was good, and he separated the light from the darkness."
    ]

def get_references():
    return [
        "Genesis 1:1",
        "Genesis 1:3",
        "Genesis 1:4"
    ]

def get_current_verse(index):
    verses = get_verses()
    return verses[index] if 0 <= index < len(verses) else "Invalid index"

def get_current_reference(index):
    references = get_references()
    return references[index] if 0 <= index < len(references) else "Invalid reference"

def next_verse(index):
    index += 1
    verses = get_verses()
    if index >= len(verses):
        index = len(verses) - 1
    return get_current_verse(index), get_current_reference(index), index

def previous_verse(index):
    index -= 1
    if index < 0:
        index = 0
    return get_current_verse(index), get_current_reference(index), index

# Interface components
with gr.Blocks() as demo:
    # Choose the translation
    translation_dropdown = gr.Dropdown(
        choices=loaded_outputs,
        label="Choose a translation",
        value=loaded_outputs[0] if loaded_outputs else None
    )
    with gr.Tabs():
        with gr.Tab("Browse"):
            current_index = gr.Number(value=0, label="Current Index", interactive=False, visible=False)
            current_reference = gr.Textbox(value=get_current_reference(0), label="Current Reference", interactive=False)
            current_verse = gr.Textbox(value=get_current_verse(0), label="Current Verse", interactive=False)
            with gr.Row():
                prev_button = gr.Button("Previous")
                next_button = gr.Button("Next")
            
            prev_button.click(previous_verse, inputs=current_index, outputs=[current_verse, current_reference, current_index])
            next_button.click(next_verse, inputs=current_index, outputs=[current_verse, current_reference, current_index])

        with gr.Tab("Add Comments"):
            gr.Textbox(value="Hello, World!", label="Add Comments")

# Launch the interface
demo.launch()
