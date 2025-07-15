import os
import time
from datetime import datetime
import json
import zlib
import base64
from collections import defaultdict


from output_formatters.pdf_report import get_literal_translation, summarize_verse_report, translate_verse_report, compute_std_devs

import yaml

from pydantic import BaseModel
from openai import OpenAI

import utils
from format_utilities import get_config_for, get_sorted_verses

def run( file ):
    """
    This export creates a single file self-contained html export
    of the file with the worse verses at the top,
    and the rest in order further down.
    """
    this_config = get_config_for( file ) or {}

    if not this_config.get( 'reports', {} ).get( 'html report enabled', False ):
        print( f"{file} does not have html report enabled" )
        return


    original_content = utils.load_jsonl(f"output/{file}")

    #now strip original_content by start_line end_line
    if "end_line" in this_config:
        end_line = this_config["end_line"]-1
        original_content = original_content[:end_line+1]
    if "start_line" in this_config:
        start_line = this_config["start_line"]-1
        original_content = original_content[start_line:]

    #get the keys
    translation_key = this_config.get( 'translation_key', ['fresh_translation','text'] )
    reference_key = this_config.get( 'reference_key', ['vref'] )
    source_key = this_config.get( 'source_key', ['source'] )

    report_first_iteration = this_config.get('reports',{}).get('report first iteration', False )
    report_language = this_config.get( 'reports', {} ).get( "report language", "English" )
    target_language = this_config.get( 'markdown_format', {} ).get( "outputs", {} ).get( "target language", None )
    if target_language is None:
        target_language = this_config.get( 'reports', {} ).get( "target language", "English" )
    source_language = this_config.get( "reports", {} ).get( "source language", None )


    #now split it into books if the config requests it.
    if this_config.get( 'split_by_book', True ):
        book_to_verses = defaultdict( lambda: [] )
        for verse in original_content:
            vref = utils.look_up_key(verse, reference_key)
            book = utils.split_ref2( vref )[0]
            book_to_verses[book].append( verse )
    else:
        book_to_verses = { "": original_content }

    # Sorting by grade is handled in the HTML file with javascript.



    #Get the output folder ready.
    base_filename = this_config.get( 'output_file', os.path.splitext(file)[0] )
    output_folder = this_config.get( 'output_folder', f"output/html_reports/{base_filename}" )
    os.makedirs( output_folder, exist_ok=True )

    pdf_report_output_folder = this_config.get( 'output_folder', f"output/pdf_reports/{base_filename}" )


    num_sd_to_report = this_config.get( "pdf_reports", {} ).get( 'num_sd_to_report', 2 )
    percentage_sorted = this_config.get( "pdf_reports", {} ).get( 'percentage sorted', None )


    client = None
    if 'api_key' in this_config:
        with open( 'key.yaml', encoding='utf-8' ) as keys_f:
            api_keys = yaml.load(keys_f, Loader=yaml.FullLoader)
            client = OpenAI(api_key=utils.look_up_key( api_keys, this_config['api_key'] ))

    #what we report from the verse object can change based on settings so we break out all the logic
    #for that here with the r_ functions and the reporting below doesn't have to know about it.
    r_get_ref = lambda verse: utils.look_up_key(verse, reference_key)
    r_get_source = lambda verse: utils.look_up_key(verse, source_key)
    r_get_grade = get_sorted_verses( [], reference_key, sort_on_first=report_first_iteration )[1]

    def r_get_href(verse):
        ref = r_get_ref(verse)
        result = ''.join(c if c.isalnum() else '_' for c in ref)
        return result


    def r_get_translation( verse ):
        translation = utils.look_up_key(verse, translation_key)

        #if we are doing a first iteration report,
        #then let the translation be what the first reflection loop was grading.
        #also the grade is that.
        if report_first_iteration:
            reflection_loop = verse.get( 'reflection_loops', [] )
            if reflection_loop:
                first_loop = reflection_loop[0]
                graded_verse = first_loop.get( 'graded_verse', '' )
                if graded_verse:
                    if graded_verse != translation:
                        translation = graded_verse

        return translation

    def r_get_grades( verse ):
        translation = r_get_translation( verse )
        reflection_loops = verse.get('reflection_loops', [])

        #iterate through the loops backwards and if we find a matching
        #verse that is what we want, otherwise return the last one and
        #other wise just return an empty list.
        if not reflection_loops: return []
        for loop in reversed( reflection_loops ):
            if loop.get( 'graded_verse', '' ) == translation:
                return loop.get( 'grades', [] )

        return reflection_loops[-1].get( 'grades', [] )

    r_translation_is_report_language = report_language == target_language

    def r_get_label( label ):
        if report_language == "English": return label
        return r_get_label_wrapped( label, report_language )

    @utils.cache_decorator( f"{pdf_report_output_folder}_cache/labels", enabled=client is not None )
    def r_get_label_wrapped( label, to_language ):
        if to_language == "English": return label

        system_message = "You are a translation consultant, creating labels in a target language"
        user_message_array = []
        user_message_array += [ "Translate the following label into " + to_language + " preserving the markdown formating:" ]

        user_message_array += [ "\n", json.dumps( {"label": label}, ensure_ascii=False ) ]
        user_message = "".join(user_message_array)

        if not client: return label

        class LabelResponse(BaseModel):
            translated_label: str

        completion = utils.use_model( client,
            model=this_config.get( 'model', 'gpt-4o-mini' ),
            messages=[
                { "role": "system", "content": system_message },
                { "role": "user", "content": user_message }
            ],
            temperature=this_config.get('temperature', 1.2),
            top_p=this_config.get('top_p', 0.9),
            response_format=LabelResponse
        )

        model_dump = completion.choices[0].message.parsed.model_dump()
        translated_label = model_dump['translated_label']

        #don't let the model add markdown markers.
        if "*" not in label and "*" in translated_label:
            translated_label = translated_label.replace("*", "")

        if label.startswith( "**" ):
            if not translated_label.startswith( "**" ):
                translated_label = "**" + translated_label

        if label.startswith( "### " ):
            if not translated_label.startswith( "### " ):
                translated_label = "### " + translated_label

        if label.endswith( "**" ):
            if not translated_label.endswith( "**" ):
                translated_label = translated_label + "**"

        if label.endswith( "**:" ):
            if not translated_label.endswith( "**:" ):
                translated_label = translated_label + "**:"

        return translated_label

    def r_get_literal_translation( text, from_language=None, to_language=None ):
        if not client: return text

        if to_language is None:
            to_language = this_config.get( 'reports', {} ).get("report language", "English" )

        if this_config.get( 'html_reports', {} ).get( 'hide_source_language_in_back_translations', False ):
            from_language = None

        return r_get_literal_translation_wrapped( text, from_language, to_language )

    @utils.cache_decorator( f"{pdf_report_output_folder}_cache/literal_translation", enabled=client is not None )
    def r_get_literal_translation_wrapped( text, from_language, to_language ):
        return get_literal_translation( client, this_config, text, from_language, to_language )

    @utils.cache_decorator( f"{pdf_report_output_folder}_cache/summerization", enabled=client is not None )
    def r_run_summary( raw_report, to_language ):
        return summarize_verse_report( client, raw_report, this_config.get( "reports", {} ), just_summarize=True, no_label=True, output_in_markdown=False, to_language=to_language )


    @utils.cache_decorator( f"{pdf_report_output_folder}_cache/parenthesis_translation", enabled=client is not None )
    def r_add_parenthesis_translation( text, to_language ):
        if text:
            return translate_verse_report( client, text, this_config.get( "reports", {} ), to_language=to_language )
        return text

    def r_get_translation_translated( verse ):
        if target_language != report_language:
            if r_get_translation(verse):
                return r_get_literal_translation( r_get_translation(verse), from_language=target_language, to_language=report_language )
        return None

    def r_get_source_translated( verse ):
        if source_language != report_language:
            if r_get_source(verse):
                return r_get_literal_translation( r_get_source(verse), from_language=source_language, to_language=report_language )
        return None

    def r_get_suggested_translation_translated( verse ):
        if target_language != report_language:
            if r_get_suggested_translation( verse ):
                return r_get_literal_translation( r_get_suggested_translation( verse ), from_language=target_language, to_language=report_language )
        return None

    def r_get_review( verse ):
        grades = r_get_grades( verse )

        raw_report_array = []
        for grade_i,grade in enumerate(grades):
            raw_report_array.append( "**" + r_get_label("Review" ) + f" {grade_i+1}** " )
            raw_report_array.append( "_(" + r_get_label("Grade" ) + f" {grade['grade']})_: {grade['comment']}\n\n" )
        raw_report = "".join(raw_report_array)

        summarized_report = r_run_summary( raw_report, to_language=report_language )

        #also add in translations
        translated_report = r_add_parenthesis_translation( summarized_report, to_language=report_language )

        return translated_report

    if "suggested_translation" in this_config.get( "reports", {} ):
        suggested_translation_filename = this_config["reports"]["suggested_translation"]
        if not suggested_translation_filename.endswith( ".jsonl" ):
            suggested_translation_filename += ".jsonl"
        suggested_translation = utils.load_jsonl( os.path.join( "output", suggested_translation_filename ) )
        hashed_suggested_translation = { utils.look_up_key( x, reference_key ): x for x in suggested_translation }
    else:
        hashed_suggested_translation = None
    def r_get_suggested_translation( verse ):
        if hashed_suggested_translation:
            return hashed_suggested_translation.get( r_get_ref(verse) )

        if report_first_iteration:
            last_translation = utils.look_up_key(verse, translation_key)
            if last_translation and last_translation != r_get_translation(verse):
                return last_translation

        return None

    #now we will loop through the book names.
    for book, verses in book_to_verses.items():
        report_data = []

        html_name = book if book else base_filename

        html_prefix = this_config.get( "html_reports", {} ).get( "output_prefix", "" )
        if html_prefix:
            html_name = f"{html_prefix}{html_name}"

        output_filename = f"{output_folder}/{html_name}.html"

        # --- Title Page ---
        title = this_config.get( "html_reports", {} ).get( "title", f"{base_filename} {book} Report").format( book=book )


        start_time = time.time()
        #now iterate through all the verses in natural order.
        for verse_i,verse in enumerate(book_to_verses[book]):

            current_time = time.time()
            elapsed_time = current_time - start_time
            # estimated_end_time = len(book_to_verses[book])/(verse_i+1) * elapsed_time + current_time

            # Calculate estimated total time needed
            estimated_total_time = len(book_to_verses[book]) / (verse_i + 1) * elapsed_time
            # Estimated end time is start time + total estimated duration
            estimated_end_time = start_time + estimated_total_time

            print( f"Processing verse {verse_i+1} of {len(book_to_verses[book])} - {elapsed_time:.2f} seconds elapsed - estimated {estimated_end_time - current_time:.2f} seconds left, estimated end time {datetime.fromtimestamp(estimated_end_time).strftime('%Y-%m-%d %I:%M:%S %p')}" )

            verse_data = {
                "vref": r_get_ref(verse),
                "href": r_get_href(verse),
                "grade": r_get_grade(verse),
                "source": r_get_source(verse),
                "translation": r_get_translation(verse),
                "suggested_translation": r_get_suggested_translation(verse),
                "review": r_get_review(verse)
            }
            if r_get_source_translated(verse):
                verse_data["source_translated"] = r_get_source_translated(verse)
            if r_get_translation_translated(verse):
                verse_data["translation_translated"] = r_get_translation_translated(verse)
            if r_get_suggested_translation_translated(verse):
                verse_data["suggested_translation_translated"] = r_get_suggested_translation_translated(verse)

            report_data.append(verse_data)

        # Read and encode the font
        font_path = 'fonts/NotoSans-Regular.ttf'
        if os.path.exists(font_path):
            with open(font_path, 'rb') as f:
                font_data = f.read()
            base64_font = base64.b64encode(font_data).decode('utf-8')
        else:
            base64_font = ''

        json_string = json.dumps(report_data, ensure_ascii=False)
        compress_obj = zlib.compressobj(level=-1, method=zlib.DEFLATED, wbits=-15)
        compressed_data = compress_obj.compress(json_string.encode('utf-8'))
        compressed_data += compress_obj.flush()
        base64_data = base64.b64encode(compressed_data).decode('utf-8')
        html_content = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{title}</title>
    <style>
        @font-face {{
            font-family: 'NotoSans';
            src: url(data:font/truetype;charset=utf-8;base64,{base64_font}) format('truetype');
            font-weight: normal;
            font-style: normal;
        }}
        body {{
            font-family: 'NotoSans', sans-serif;
            background-color: #f4f4f9;
            color: #333;
            margin: 0;
            padding: 60px 20px 20px 20px;
            line-height: 1.6;
            font-size: 16px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #fff;
            padding: 20px 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        /* Sticky Navigation Bar */
        .nav-bar {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 40px;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 20px;
            z-index: 1000;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .nav-links {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}
        
        .nav-link {{
            color: #0056b3;
            text-decoration: none;
            font-weight: 500;
            font-size: 14px;
            padding: 8px 12px;
            border-radius: 4px;
            transition: background-color 0.2s ease;
        }}
        
        .nav-link:hover {{
            background-color: rgba(0, 86, 179, 0.1);
        }}
        
        .hamburger {{
            display: flex;
            flex-direction: column;
            cursor: pointer;
            padding: 4px;
            gap: 3px;
        }}
        
        .hamburger span {{
            width: 20px;
            height: 2px;
            background-color: #333;
            transition: all 0.3s ease;
        }}
        
        .hamburger.active span:nth-child(1) {{
            transform: rotate(45deg) translate(5px, 5px);
        }}
        
        .hamburger.active span:nth-child(2) {{
            opacity: 0;
        }}
        
        .hamburger.active span:nth-child(3) {{
            transform: rotate(-45deg) translate(7px, -6px);
        }}
        
        /* Sidebar */
        .sidebar-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 1500;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s ease, visibility 0.3s ease;
        }}
        
        .sidebar-overlay.active {{
            opacity: 1;
            visibility: visible;
        }}
        
        .sidebar {{
            position: fixed;
            top: 0;
            left: -320px;
            width: 320px;
            height: 100vh;
            background: #fff;
            z-index: 1600;
            transition: left 0.3s ease;
            overflow-y: auto;
            box-shadow: 2px 0 10px rgba(0,0,0,0.1);
        }}
        
        .sidebar.active {{
            left: 0;
        }}
        
        .sidebar-header {{
            padding: 20px;
            border-bottom: 1px solid #e0e0e0;
            background: #f8f9fa;
        }}
        
        .sidebar-header h3 {{
            margin: 0;
            color: #333;
            font-size: 18px;
        }}
        
        .sidebar-content {{
            padding: 20px;
        }}
        
        .sidebar-section {{
            margin-bottom: 20px;
        }}
        
        .sidebar-section h4 {{
            margin: 0 0 10px 0;
            color: #0056b3;
            font-size: 16px;
            border-bottom: 1px solid #e0e0e0;
            padding-bottom: 5px;
        }}
        
        .sidebar-link {{
            display: block;
            color: #333;
            text-decoration: none;
            padding: 8px 12px;
            border-radius: 4px;
            margin-bottom: 2px;
            transition: background-color 0.2s ease;
        }}
        
        .sidebar-link:hover {{
            background-color: #f0f0f0;
        }}
        
        .sidebar-link.chapter {{
            padding-left: 24px;
            font-size: 14px;
            color: #666;
        }}
        
        @media (max-width: 600px) {{
            body {{
                font-size: 20px;
                padding-top: 90px;
                padding-left: 15px;
                padding-right: 15px;
                width: 100vw;
                max-width: 100vw;
                overflow-x: hidden;
            }}
            
            .container {{
                padding: 15px 20px;
                max-width: 100vw !important;
                width: 100vw !important;
                margin: 0 !important;
                box-sizing: border-box;
            }}
            
            .nav-links {{
                gap: 10px;
            }}
            
            .nav-link {{
                font-size: 24px !important;
                padding: 12px 14px;
            }}
            
            .nav-link .text {{
                display: none;
            }}
            
            .nav-link .icon {{
                display: inline;
                font-size: 30px !important;
            }}
            
            .sidebar {{
                width: 85vw;
                left: -85vw;
            }}
            
            .sidebar-header {{
                padding: 30px;
            }}
            
            .sidebar-header h3 {{
                font-size: 30px !important;
                margin: 0;
            }}
            
            .sidebar-section {{
                margin-bottom: 30px;
            }}
            
            .sidebar-section h4 {{
                font-size: 26px !important;
                margin: 0 0 20px 0;
                padding-bottom: 10px;
            }}
            
            .sidebar-link {{
                font-size: 24px !important;
                padding: 18px 25px;
                margin-bottom: 8px;
            }}
            
            .sidebar-link.chapter {{
                font-size: 22px !important;
                padding: 16px 20px 16px 50px;
            }}
            
            .hamburger {{
                padding: 16px;
            }}
            
            .hamburger span {{
                width: 32px;
                height: 5px;
                gap: 5px;
            }}
            
            .nav-bar {{
                height: 90px;
                padding: 0 15px;
                width: 100%;
                box-sizing: border-box;
            }}
            
            h1 {{
                font-size: 2.4em;
            }}
            
            h2 {{
                font-size: 1.8em;
            }}
            
            .verse {{
                padding: 25px;
                margin-bottom: 25px;
                font-size: 1.1em;
            }}
            
            .vref {{
                font-size: 1.5em;
            }}
            
            .grade {{
                font-size: 1em;
            }}
            
            .label {{
                font-size: 1.2em;
                margin-top: 15px;
            }}
            
            #download-jsonl {{
                font-size: 1.2em;
                padding: 15px 30px;
            }}
            
            /* Keep heat map text small as requested */
            .heat-map-label {{
                font-size: 0.85em;
            }}
            
            .heat-map-square {{
                font-size: 9px;
                width: 20px;
                height: 20px;
            }}
            
            /* Ensure full width usage */
            #heat-map-content {{
                padding: 10px;
            }}
            
            /* Settings panel adjustments */
            #settings-panel.expanded {{
                padding: 20px 15px;
            }}
            
            .setting-row {{
                margin-bottom: 20px;
            }}
            
            .setting-row label {{
                font-size: 1.05em;
            }}
        }}
        
        @media (min-width: 601px) {{
            .nav-link .icon {{
                display: none;
            }}
        }}
        h1, h2 {{
            color: #444;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        h1 {{
            text-align: center;
            font-size: 2.5em;
        }}
        h2 {{
            font-size: 1.8em;
        }}
        .verse {{
            border: 1px solid #e0e0e0;
            background-color: #fafafa;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        }}
        .vref {{
            font-weight: bold;
            font-size: 1.4em;
            color: #0056b3;
        }}
        .grade {{
            font-style: italic;
            color: #555;
            font-size: 0.9em;
        }}
        .label {{
            font-weight: bold;
            color: #333;
            margin-top: 10px;
            display: block;
        }}
        #heat-map-content {{
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 5px;
            margin-bottom: 20px;
            background: #fdfdfd;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #eee;
        }}
        .heat-map-row {{
            display: contents;
        }}
        .heat-map-label {{
            font-weight: bold;
            text-align: right;
            padding-right: 10px;
            align-self: center;
        }}
        .heat-map-verses {{
            display: flex;
            flex-wrap: wrap;
            gap: 3px;
        }}
        .heat-map-square {{
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: black;
            text-decoration: none;
            font-size: 11px;
            border-radius: 4px;
            transition: transform 0.1s ease-in-out, background-color 0.3s ease;
        }}
        .heat-map-square:hover {{
            transform: scale(1.2);
            z-index: 10;
        }}
        #download-jsonl {{
            display: block;
            margin: 20px auto;
            padding: 10px 20px;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1em;
        }}
        #download-jsonl:hover {{
            background-color: #0056b3;
        }}
        .heat-map-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .heat-map-header h2 {{
            margin: 0;
        }}
        #settings-container {{
            display: inline-block;
        }}
        #settings-toggle {{
            background: #eee;
            border: 1px solid #ccc;
            border-radius: 5px;
            padding: 2px 8px;
            cursor: pointer;
            font-size: 1.5em;
            line-height: 1;
            transition: background-color 0.2s ease;
        }}
        #settings-toggle:hover {{
            background-color: #ddd;
        }}
        #settings-panel {{
            border: 1px solid #ccc;
            border-radius: 8px;
            padding: 0 20px;
            margin-top: 10px;
            margin-bottom: 0;
            background: #f9f9f9;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            max-height: 0;
            overflow: hidden;
            opacity: 0;
            transition: max-height 0.3s ease, opacity 0.3s ease, padding 0.3s ease, margin 0.3s ease;
        }}
        #settings-panel.expanded {{
            max-height: 1000px;
            opacity: 1;
            padding: 20px;
            margin-bottom: 20px;
        }}
        .setting-row {{
            display: grid;
            grid-template-columns: auto 1fr;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
        }}
        .setting-row.color-row {{
            grid-template-columns: auto auto auto auto;
        }}
        .setting-row label {{
            font-weight: bold;
            white-space: nowrap;
        }}
        @media (max-width: 600px) {{
            .setting-row {{
                grid-template-columns: 1fr;
                gap: 5px;
            }}
            .setting-row.color-row {{
                grid-template-columns: 1fr 1fr;
                gap: 10px;
            }}
            .setting-row.color-row > label:first-child,
            .setting-row.color-row > label:nth-child(3) {{
                grid-column: 1 / -1;
            }}
            #settings-panel {{
                padding: 15px;
            }}
            .container {{
                padding: 10px 20px;
            }}
        }}
        #presets button {{
            background-color: #e0e0e0;
            border: 1px solid #ccc;
            border-radius: 4px;
            padding: 5px 10px;
            cursor: pointer;
            margin-right: 5px;
        }}
        #presets button:hover {{
            background-color: #d0d0d0;
        }}
        #legend {{
            margin-bottom: 10px;
            padding: 10px;
            border: 1px solid #eee;
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <!-- Sticky Navigation Bar -->
    <nav class="nav-bar">
        <div class="hamburger" id="hamburger">
            <span></span>
            <span></span>
            <span></span>
        </div>
        <div class="nav-links">
            <a href="#heat-map" class="nav-link">
                <span class="icon">🗺️</span>
                <span class="text">{r_get_label("Heat Map")}</span>
            </a>
            <a href="#poor-verses" class="nav-link">
                <span class="icon">⚠️</span>
                <span class="text">{r_get_label("Poor Verses")}</span>
            </a>
            <a href="#all-verses" class="nav-link">
                <span class="icon">📖</span>
                <span class="text">{r_get_label("All Verses")}</span>
            </a>
            <a href="#top" class="nav-link">
                <span class="icon">⬆️</span>
                <span class="text">{r_get_label("Top")}</span>
            </a>
        </div>
    </nav>

    <!-- Sidebar Overlay -->
    <div class="sidebar-overlay" id="sidebar-overlay"></div>
    
    <!-- Sidebar -->
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h3>{r_get_label("Table of Contents")}</h3>
        </div>
        <div class="sidebar-content" id="sidebar-content">
            <!-- Content will be populated by JavaScript -->
        </div>
    </div>

    <div class="container" id="top">
        <!-- Debug Information -->
        <h1>{title}</h1>
        <p>{r_get_label("Generated on")}: {datetime.today().strftime('%B %d, %Y')}</p>
        <button id="download-jsonl">{r_get_label("Download JSONL")}</button>
        
        <div class="heat-map-header">
            <h2 id="heat-map">{r_get_label("Grade Heat Map")}</h2>
            <div id="settings-container">
                <button id="settings-toggle" title="{r_get_label("Settings")}">...</button>
            </div>
        </div>
        <div id="settings-panel">
            <h3>{r_get_label("Heat Map Settings")}</h3>
            <div class="setting-row">
                <label for="color-mode-fade">{r_get_label("Color Mode")}:</label>
                <label><input type="checkbox" id="color-mode-fade"> {r_get_label("Use fade instead of spectrum")}</label>
            </div>
            <div class="setting-row color-row">
                <label for="low-color">{r_get_label("Low Grade Color")}:</label>
                <input type="color" id="low-color">
                <label for="high-color">{r_get_label("High Grade Color")}:</label>
                <input type="color" id="high-color">
            </div>
            <div class="setting-row">
                <label for="low-grade-slider">{r_get_label("Low Grade")}:</label>
                <input type="range" id="low-grade-slider" min="0" max="100" step="1">
                <span id="low-grade-value"></span>
                <label><input type="checkbox" id="low-grade-auto"> {r_get_label("Auto")}</label>
            </div>
            <div class="setting-row">
                <label for="high-grade-slider">{r_get_label("High Grade")}:</label>
                <input type="range" id="high-grade-slider" min="0" max="100" step="1">
                <span id="high-grade-value"></span>
                <label><input type="checkbox" id="high-grade-auto"> {r_get_label("Auto")}</label>
            </div>
            <div class="setting-row">
                <label>{r_get_label("Presets")}:</label>
                <div id="presets">
                    <button data-preset="1">{r_get_label("Red-Green")}</button>
                    <button data-preset="2">{r_get_label("Neutral")}</button>
                    <button data-preset="3">{r_get_label("Diverging")}</button>
                    <button data-preset="4">{r_get_label("Monochrome")}</button>
                    <button data-preset="5">{r_get_label("The Blues")}</button>
                    <button data-preset="6">{r_get_label("Rainbow")}</button>
                </div>
            </div>
            <button id="collapse-settings">{r_get_label("Close Settings")}</button>
        </div>
        <div id="legend"></div>
        <div id="heat-map-content"></div>

        <h2 id="poor-verses">{r_get_label("Poorest Graded Verses")}</h2>
        <div id="poor-verses-content"></div>

        <h2 id="all-verses">{r_get_label("All Verses")}</h2>
        <div id="all-verses-content"></div>
    </div>

    <script>
        const base64Data = '{base64_data}';
        const compressedData = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
        
        async function decompressData(data) {{
            const ds = new DecompressionStream('deflate-raw');
            const writer = ds.writable.getWriter();
            writer.write(data);
            writer.close();
            
            const reader = ds.readable.getReader();
            let jsonString = '';
            while (true) {{
                const {{ value, done }} = await reader.read();
                if (done) break;
                jsonString += new TextDecoder().decode(value);
            }}
            return JSON.parse(jsonString);
        }}

        decompressData(compressedData).then(reportData => {{
            const num_sd_to_report = {num_sd_to_report};
            const percentage_sorted = {percentage_sorted if percentage_sorted is not None else 'null'};

            const poorVersesContent = document.getElementById('poor-verses-content');
            const allVersesContent = document.getElementById('all-verses-content');
            const heatMapContent = document.getElementById('heat-map-content');
            const legendContent = document.getElementById('legend');
            const sidebarContent = document.getElementById('sidebar-content');
            
            // Navigation functionality
            const hamburger = document.getElementById('hamburger');
            const sidebar = document.getElementById('sidebar');
            const sidebarOverlay = document.getElementById('sidebar-overlay');
            
            function toggleSidebar() {{
                hamburger.classList.toggle('active');
                sidebar.classList.toggle('active');
                sidebarOverlay.classList.toggle('active');
                document.body.style.overflow = sidebar.classList.contains('active') ? 'hidden' : '';
            }}
            
            function closeSidebar() {{
                hamburger.classList.remove('active');
                sidebar.classList.remove('active');
                sidebarOverlay.classList.remove('active');
                document.body.style.overflow = '';
            }}
            
            hamburger.addEventListener('click', toggleSidebar);
            sidebarOverlay.addEventListener('click', closeSidebar);
            
            // Close sidebar on ESC key
            document.addEventListener('keydown', (e) => {{
                if (e.key === 'Escape' && sidebar.classList.contains('active')) {{
                    closeSidebar();
                }}
            }});

            // --- Settings ---
            const settingsPanel = document.getElementById('settings-panel');
            const settingsToggleBtn = document.getElementById('settings-toggle');
            const collapseSettingsBtn = document.getElementById('collapse-settings');
            const colorModeFadeCheck = document.getElementById('color-mode-fade');
            const lowColorPicker = document.getElementById('low-color');
            const highColorPicker = document.getElementById('high-color');
            const lowGradeSlider = document.getElementById('low-grade-slider');
            const highGradeSlider = document.getElementById('high-grade-slider');
            const lowGradeValue = document.getElementById('low-grade-value');
            const highGradeValue = document.getElementById('high-grade-value');
            const lowGradeAutoCheck = document.getElementById('low-grade-auto');
            const highGradeAutoCheck = document.getElementById('high-grade-auto');
            const presetsContainer = document.getElementById('presets');

            let settings = {{
                colorMode: 'spectrum', // 'spectrum' or 'fade'
                lowColor: '#ff0000',
                highColor: '#00ff00',
                lowGrade: 0,
                highGrade: 100,
                autoLowGrade: true,
                autoHighGrade: true,
            }};

            function saveSettings() {{
                try {{
                    localStorage.setItem('reportSettings', JSON.stringify(settings));
                }} catch (e) {{
                    console.error("Could not save settings to localStorage", e);
                }}
            }}

            function loadSettings() {{
                try {{
                    const savedSettings = localStorage.getItem('reportSettings');
                    if (savedSettings) {{
                        const loadedSettings = JSON.parse(savedSettings);
                        Object.assign(settings, loadedSettings);
                    }}
                }} catch (e) {{
                    console.error("Could not load settings from localStorage", e);
                }}
            }}

            function hexToRgb(hex) {{
                var result = /^#?([a-f\d]{{2}})([a-f\d]{{2}})([a-f\d]{{2}})$/i.exec(hex);
                return result ? {{
                    r: parseInt(result[1], 16),
                    g: parseInt(result[2], 16),
                    b: parseInt(result[3], 16)
                }} : null;
            }}

            function hexToHsl(hex) {{
                const rgb = hexToRgb(hex);
                if (!rgb) return {{ h: 0, s: 0, l: 0 }};
                let r = rgb.r / 255, g = rgb.g / 255, b = rgb.b / 255;
                const max = Math.max(r, g, b), min = Math.min(r, g, b);
                let h, s, l = (max + min) / 2;
                if (max === min) {{
                    h = s = 0; // achromatic
                }} else {{
                    const d = max - min;
                    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
                    switch (max) {{
                        case r: h = (g - b) / d + (g < b ? 6 : 0); break;
                        case g: h = (b - r) / d + 2; break;
                        case b: h = (r - g) / d + 4; break;
                    }}
                    h /= 6;
                }}
                return {{ h: h * 360, s: s, l: l }};
            }}

            function gradeToColor(grade, minGrade, maxGrade) {{
                const low = settings.autoLowGrade ? minGrade : settings.lowGrade;
                const high = settings.autoHighGrade ? maxGrade : settings.highGrade;

                if (high <= low) return {{ backgroundColor: settings.lowColor, textColor: getTextColor(settings.lowColor) }};

                const normalized = (grade - low) / (high - low);
                const clampedNormalized = Math.max(0, Math.min(1, normalized));

                let backgroundColor;
                if (settings.colorMode === 'fade') {{
                    const lowRGB = hexToRgb(settings.lowColor);
                    const highRGB = hexToRgb(settings.highColor);
                    if (!lowRGB || !highRGB) return {{ backgroundColor: '#ccc', textColor: 'black' }};
                    const r = Math.round(lowRGB.r + (highRGB.r - lowRGB.r) * clampedNormalized);
                    const g = Math.round(lowRGB.g + (highRGB.g - lowRGB.g) * clampedNormalized);
                    const b = Math.round(lowRGB.b + (highRGB.b - lowRGB.b) * clampedNormalized);
                    backgroundColor = `rgb(${{r}}, ${{g}}, ${{b}})`;
                    
                    // For RGB, we can calculate luminance directly
                    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
                    const textColor = luminance > 0.5 ? 'black' : 'white';
                    return {{ backgroundColor, textColor }};
                }} else {{ // spectrum
                    const lowHsl = hexToHsl(settings.lowColor);
                    const highHsl = hexToHsl(settings.highColor);
                    let hueDiff = highHsl.h - lowHsl.h;
                    const hue = lowHsl.h + hueDiff * clampedNormalized;
                    backgroundColor = `hsl(${{hue}}, 80%, 60%)`;
                    
                    // For HSL with 60% lightness, we can determine text color more simply
                    const textColor = 'black'; // 60% lightness is generally light enough for black text
                    return {{ backgroundColor, textColor }};
                }}
            }}

            function updateHeatMapAndLegend() {{
                const allGrades = reportData.map(v => v.grade);
                const minGrade = Math.min(...allGrades);
                const maxGrade = Math.max(...allGrades);
                document.querySelectorAll('.heat-map-square').forEach(square => {{
                    const vref = square.getAttribute('data-vref');
                    const verse = reportData.find(v => v.vref === vref);
                    if (verse) {{
                        const colors = gradeToColor(verse.grade, minGrade, maxGrade);
                        square.style.backgroundColor = colors.backgroundColor;
                        square.style.color = colors.textColor;
                    }}
                }});

                // Update Legend
                const legendMin = settings.autoLowGrade ? Math.floor(minGrade) : settings.lowGrade;
                const legendMax = settings.autoHighGrade ? Math.ceil(maxGrade) : settings.highGrade;

                let gradient;
                if (settings.colorMode === 'fade') {{
                    gradient = `linear-gradient(to right, ${{settings.lowColor}}, ${{settings.highColor}})`;
                }} else {{
                    const lowHsl = hexToHsl(settings.lowColor);
                    const highHsl = hexToHsl(settings.highColor);
                    let hueDiff = highHsl.h - lowHsl.h;
                    const stops = [];
                    for (let i = 0; i <= 10; i++) {{
                        const normalized = i / 10;
                        const hue = lowHsl.h + hueDiff * normalized;
                        stops.push(`hsl(${{hue}}, 80%, 60%)`);
                    }}
                    gradient = `linear-gradient(to right, ${{stops.join(', ')}})`;
                }}

                legendContent.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span>${{legendMin.toFixed(0)}}</span>
                        <div style="flex-grow: 1; height: 20px; background: ${{gradient}}; border-radius: 5px;"></div>
                        <span>${{legendMax.toFixed(0)}}</span>
                    </div>
                `;
            }}
            
            function updateControlsFromSettings() {{
                colorModeFadeCheck.checked = settings.colorMode === 'fade';
                lowColorPicker.value = settings.lowColor;
                highColorPicker.value = settings.highColor;
                lowGradeSlider.value = settings.lowGrade;
                highGradeSlider.value = settings.highGrade;
                lowGradeValue.textContent = settings.lowGrade;
                highGradeValue.textContent = settings.highGrade;
                lowGradeAutoCheck.checked = settings.autoLowGrade;
                highGradeAutoCheck.checked = settings.autoHighGrade;
                lowGradeSlider.disabled = settings.autoLowGrade;
                highGradeSlider.disabled = settings.autoHighGrade;
            }}

            function applyPreset(presetId) {{
                switch(String(presetId)) {{
                    case '1': // Red-Green (Red=bad, Green=good)
                        settings.colorMode = 'spectrum';
                        settings.lowColor = '#ff0000';
                        settings.highColor = '#00ff00';
                        break;
                    case '2': // Neutral sequential
                        settings.colorMode = 'fade';
                        settings.lowColor = '#FDE725';
                        settings.highColor = '#440154';
                        break;
                    case '3': // Traditional diverging
                        settings.colorMode = 'fade';
                        settings.lowColor = '#2166AC';
                        settings.highColor = '#B2182B';
                        break;
                    case '4': // Monochrome
                        settings.colorMode = 'fade';
                        settings.lowColor = '#F7FBFF';
                        settings.highColor = '#08306B';
                        break;
                    case '5': // The Blues
                        settings.colorMode = 'fade';
                        settings.lowColor = '#ADD8E6';
                        settings.highColor = '#00008B';
                        break;
                    case '6': // Rainbow (Violet=worst, Red=best)
                        settings.colorMode = 'spectrum';
                        settings.lowColor = '#ee82ee'; // Violet
                        settings.highColor = '#ff0000'; // Red
                        break;
                }}
                updateControlsFromSettings();
                updateHeatMapAndLegend();
                saveSettings();
            }}

            function setupEventListeners() {{
                settingsToggleBtn.addEventListener('click', () => {{
                    const isExpanded = settingsPanel.classList.contains('expanded');
                    if (isExpanded) {{
                        settingsPanel.classList.remove('expanded');
                        settingsToggleBtn.textContent = '...';
                        settingsToggleBtn.title = 'Settings';
                    }} else {{
                        settingsPanel.classList.add('expanded');
                        settingsToggleBtn.innerHTML = '&times;';
                        settingsToggleBtn.title = 'Close Settings';
                    }}
                }});
                collapseSettingsBtn.addEventListener('click', () => {{
                    settingsPanel.classList.remove('expanded');
                    settingsToggleBtn.textContent = '...';
                    settingsToggleBtn.title = 'Settings';
                }});

                const update = () => {{
                    settings.colorMode = colorModeFadeCheck.checked ? 'fade' : 'spectrum';
                    settings.lowColor = lowColorPicker.value;
                    settings.highColor = highColorPicker.value;
                    settings.lowGrade = parseInt(lowGradeSlider.value, 10);
                    settings.highGrade = parseInt(highGradeSlider.value, 10);
                    settings.autoLowGrade = lowGradeAutoCheck.checked;
                    settings.autoHighGrade = highGradeAutoCheck.checked;
                    updateControlsFromSettings();
                    updateHeatMapAndLegend();
                    saveSettings();
                }};

                [colorModeFadeCheck, lowColorPicker, highColorPicker, lowGradeAutoCheck, highGradeAutoCheck].forEach(el => el.addEventListener('change', update));
                [lowGradeSlider, highGradeSlider].forEach(el => el.addEventListener('input', (e) => {{
                    if (e.target.id === 'low-grade-slider') lowGradeValue.textContent = e.target.value;
                    if (e.target.id === 'high-grade-slider') highGradeValue.textContent = e.target.value;
                    update();
                }}));
                
                presetsContainer.addEventListener('click', (e) => {{
                    if (e.target.tagName === 'BUTTON') {{
                        applyPreset(e.target.dataset.preset);
                    }}
                }});
            }}

            function splitRef(reference) {{
                const lastSpaceIndex = reference.lastIndexOf(' ');
                if (lastSpaceIndex === -1) return [reference, null, null];
                const bookSplit = reference.substring(0, lastSpaceIndex);
                const chapterVerseStr = reference.substring(lastSpaceIndex + 1);
                if (!chapterVerseStr.includes(':')) return [bookSplit, parseInt(chapterVerseStr), null];
                const [chapterNum, verseNum] = chapterVerseStr.split(':');
                if (verseNum.includes('-')) {{
                    const [startVerse, endVerse] = verseNum.split('-').map(Number);
                    return [bookSplit, parseInt(chapterNum), startVerse, endVerse];
                }}
                return [bookSplit, parseInt(chapterNum), parseInt(verseNum), parseInt(verseNum)];
            }}

            function renderVerse(verse, isPoor) {{
                const verseDiv = document.createElement('div');
                verseDiv.className = 'verse';
                if (!isPoor) {{
                    verseDiv.id = verse.href;
                }}

                let vref_html = isPoor ? `<a href="#${{verse.href}}">${{verse.vref}}</a>` : verse.vref;

                verseDiv.innerHTML = `
                    <div class="vref">${{vref_html}} <span class="grade">({r_get_label("Grade")}: ${{verse.grade.toFixed(1)}})</span></div>
                    <div><span class="label">{r_get_label("Source")}:</span> <div>${{verse.source}}</div></div>
                    ${{verse.source_translated ? `<div>(${{verse.source_translated}})</div>` : ''}}
                    <div><span class="label">{r_get_label("Translation")}:</span> <div>${{verse.translation}}</div></div>
                    ${{verse.translation_translated ? `<div>(${{verse.translation_translated}})</div>` : ''}}
                    ${{verse.suggested_translation ? `<div><span class="label">{r_get_label("Suggested Translation")}:</span><div>${{verse.suggested_translation}}</div>${{verse.suggested_translation_translated ? `<div>(${{verse.suggested_translation_translated}})</div>` : ''}}</div>` : ''}}
                    <div><span class="label">{r_get_label("Review")}:</span> <div>${{verse.review}}</div></div>
                `;
                return verseDiv;
            }}

            // --- Main Execution ---
            
            // 1. Load settings from cookie
            loadSettings();

            // 2. Initial render of static content
            const bookChapterVerses = {{}};
            reportData.forEach(verse => {{
                const [book, chapter] = splitRef(verse.vref);
                if (!bookChapterVerses[book]) bookChapterVerses[book] = {{}};
                if (!bookChapterVerses[book][chapter]) bookChapterVerses[book][chapter] = [];
                bookChapterVerses[book][chapter].push(verse);
            }});

            Object.keys(bookChapterVerses).sort().forEach(book => {{
                Object.keys(bookChapterVerses[book]).sort((a, b) => a - b).forEach(chapter => {{
                    const chapterVerses = bookChapterVerses[book][chapter];
                    chapterVerses.sort((a, b) => splitRef(a.vref)[2] - splitRef(b.vref)[2]);

                    const row = document.createElement('div');
                    row.className = 'heat-map-row';
                    const label = document.createElement('div');
                    label.className = 'heat-map-label';
                    label.textContent = `${{book}} ${{chapter}}`;
                    row.appendChild(label);

                    const versesContainer = document.createElement('div');
                    versesContainer.className = 'heat-map-verses';
                    chapterVerses.forEach(verse => {{
                        const square = document.createElement('a');
                        square.className = 'heat-map-square';
                        square.href = `#${{verse.href}}`;
                        square.setAttribute('data-vref', verse.vref);
                        square.textContent = splitRef(verse.vref)[2];
                        versesContainer.appendChild(square);
                    }});
                    row.appendChild(versesContainer);
                    heatMapContent.appendChild(row);
                }});
            }});

            let poorVerses = [];
            if (percentage_sorted !== null) {{
                const sortedByGrade = [...reportData].sort((a, b) => a.grade - b.grade);
                const count = Math.floor(percentage_sorted * reportData.length / 100);
                poorVerses = sortedByGrade.slice(0, count);
            }} else {{
                const grades = reportData.map(v => v.grade);
                if (grades.length > 1) {{
                    const mean = grades.reduce((a, b) => a + b, 0) / grades.length;
                    const stdDev = Math.sqrt(grades.map(x => Math.pow(x - mean, 2)).reduce((a, b) => a + b, 0) / (grades.length -1) );
                    const gradeCutOff = mean - num_sd_to_report * stdDev;
                    poorVerses = reportData.filter(v => v.grade <= gradeCutOff);
                    poorVerses.sort((a, b) => a.grade - b.grade);
                }}
            }}

            poorVerses.forEach(verse => poorVersesContent.appendChild(renderVerse(verse, true)));
            reportData.forEach(verse => allVersesContent.appendChild(renderVerse(verse, false)));

            // 3. Populate sidebar with table of contents
            const sidebarSections = [
                {{ title: '{r_get_label("Heat Map")}', href: '#heat-map' }},
                {{ title: '{r_get_label("Poor Verses")}', href: '#poor-verses', count: poorVerses.length }},
                {{ title: '{r_get_label("All Verses")}', href: '#all-verses' }}
            ];

            sidebarSections.forEach(section => {{
                const sectionDiv = document.createElement('div');
                sectionDiv.className = 'sidebar-section';
                
                const heading = document.createElement('h4');
                heading.innerHTML = section.title + (section.count ? ` (${{section.count}})` : '');
                sectionDiv.appendChild(heading);
                
                const link = document.createElement('a');
                link.href = section.href;
                link.className = 'sidebar-link';
                link.textContent = `{r_get_label("Go to")} ${{section.title}}`;
                sectionDiv.appendChild(link);
                
                // Add chapter links for All Verses section
                if (section.title === '{r_get_label("All Verses")}') {{
                    Object.keys(bookChapterVerses).sort().forEach(book => {{
                        Object.keys(bookChapterVerses[book]).sort((a, b) => a - b).forEach(chapter => {{
                            const chapterLink = document.createElement('a');
                            chapterLink.href = `#${{bookChapterVerses[book][chapter][0].href}}`;
                            chapterLink.className = 'sidebar-link chapter';
                            chapterLink.textContent = `${{book}} ${{chapter}}`;
                            sectionDiv.appendChild(chapterLink);
                        }});
                    }});
                }}
                
                sidebarContent.appendChild(sectionDiv);
            }});

            // 4. Add smooth scrolling for all navigation links
            document.addEventListener('click', (e) => {{
                if (e.target.matches('a[href^="#"]')) {{
                    e.preventDefault();
                    const target = document.querySelector(e.target.getAttribute('href'));
                    if (target) {{
                        target.scrollIntoView({{
                            behavior: 'smooth',
                            block: 'start'
                        }});
                        // Close sidebar if open
                        if (sidebar.classList.contains('active')) {{
                            closeSidebar();
                        }}
                    }}
                }}
            }});

            // 5. Set up UI controls and dynamic content
            updateControlsFromSettings();
            updateHeatMapAndLegend();
            setupEventListeners();

            // 4. Download button
            document.getElementById('download-jsonl').addEventListener('click', () => {{
                let jsonlContent = '';
                reportData.forEach(item => {{
                    const itemForJsonl = {{...item, grade: item.grade.toFixed(1)}};
                    jsonlContent += JSON.stringify(itemForJsonl) + '{utils.SLASH_N}';
                }});
                const blob = new Blob([jsonlContent], {{ type: 'application/jsonl' }});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = '{html_name}.jsonl';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }});
        }});
    </script>
</body>
</html>
'''
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
