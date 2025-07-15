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
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #fff;
            padding: 20px 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
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
        #heat-map {{
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
            margin-bottom: 20px;
        }}
        .heat-map-header h2 {{
            margin: 0;
        }}
        #settings-container {{
            position: relative;
        }}
        #settings-toggle {{
            background: #eee;
            border: 1px solid #ccc;
            border-radius: 5px;
            padding: 2px 8px;
            cursor: pointer;
            font-size: 1.5em;
            line-height: 1;
        }}
        #settings-panel {{
            display: none;
            border: 1px solid #ccc;
            border-radius: 8px;
            padding: 20px;
            margin-top: 10px;
            background: #f9f9f9;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            position: absolute;
            right: 0;
            z-index: 20;
            width: 400px;
        }}
        .setting-row {{
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .setting-row label {{
            font-weight: bold;
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
    <div class="container">
        <h1>{title}</h1>
        <p>Generated on: {datetime.today().strftime('%B %d, %Y')}</p>
        <button id="download-jsonl">Download JSONL</button>
        
        <div class="heat-map-header">
            <h2>Grade Heat Map</h2>
            <div id="settings-container">
                <button id="settings-toggle" title="Settings">...</button>
                <div id="settings-panel">
                    <h3>Heat Map Settings</h3>
                    <div class="setting-row">
                        <label><input type="checkbox" id="color-mode-fade"> Use fade instead of spectrum</label>
                    </div>
                    <div class="setting-row">
                        <label for="low-color">Low Grade Color:</label>
                        <input type="color" id="low-color">
                        <label for="high-color">High Grade Color:</label>
                        <input type="color" id="high-color">
                    </div>
                    <div class="setting-row">
                        <label for="low-grade-slider">Low Grade:</label>
                        <input type="range" id="low-grade-slider" min="0" max="100" step="1">
                        <span id="low-grade-value"></span>
                        <label><input type="checkbox" id="low-grade-auto"> Auto</label>
                    </div>
                    <div class="setting-row">
                        <label for="high-grade-slider">High Grade:</label>
                        <input type="range" id="high-grade-slider" min="0" max="100" step="1">
                        <span id="high-grade-value"></span>
                        <label><input type="checkbox" id="high-grade-auto"> Auto</label>
                    </div>
                    <div class="setting-row">
                        <label>Presets:</label>
                        <div id="presets">
                            <button data-preset="1">Red-Green</button>
                            <button data-preset="2">Neutral</button>
                            <button data-preset="3">Diverging</button>
                            <button data-preset="4">Monochrome</button>
                            <button data-preset="5">The Blues</button>
                            <button data-preset="6">Rainbow</button>
                        </div>
                    </div>
                    <button id="collapse-settings">Close Settings</button>
                </div>
            </div>
        </div>
        <div id="legend"></div>
        <div id="heat-map"></div>

        <h2>Poorest Graded Verses</h2>
        <div id="poor-verses"></div>

        <h2>All Verses</h2>
        <div id="all-verses"></div>
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

            const poorVersesContent = document.getElementById('poor-verses');
            const allVersesContent = document.getElementById('all-verses');
            const heatMapContent = document.getElementById('heat-map');
            const legendContent = document.getElementById('legend');

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
                document.cookie = `reportSettings=${{JSON.stringify(settings)}};path=/;max-age=31536000;samesite=strict`;
            }}

            function loadSettings() {{
                const cookie = document.cookie.split('; ').find(row => row.startsWith('reportSettings='));
                if (cookie) {{
                    try {{
                        const loadedSettings = JSON.parse(cookie.split('=')[1]);
                        Object.assign(settings, loadedSettings);
                    }} catch (e) {{
                        console.error("Could not parse settings cookie", e);
                    }}
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

                if (high <= low) return settings.lowColor;

                const normalized = (grade - low) / (high - low);
                const clampedNormalized = Math.max(0, Math.min(1, normalized));

                if (settings.colorMode === 'fade') {{
                    const lowRGB = hexToRgb(settings.lowColor);
                    const highRGB = hexToRgb(settings.highColor);
                    if (!lowRGB || !highRGB) return '#ccc';
                    const r = Math.round(lowRGB.r + (highRGB.r - lowRGB.r) * clampedNormalized);
                    const g = Math.round(lowRGB.g + (highRGB.g - lowRGB.g) * clampedNormalized);
                    const b = Math.round(lowRGB.b + (highRGB.b - lowRGB.b) * clampedNormalized);
                    return `rgb(${{r}}, ${{g}}, ${{b}})`;
                }} else {{ // spectrum
                    const lowHsl = hexToHsl(settings.lowColor);
                    const highHsl = hexToHsl(settings.highColor);
                    let hueDiff = highHsl.h - lowHsl.h;
                    const hue = lowHsl.h + hueDiff * clampedNormalized;
                    return `hsl(${{hue}}, 80%, 60%)`;
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
                        square.style.backgroundColor = gradeToColor(verse.grade, minGrade, maxGrade);
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
                    settingsPanel.style.display = settingsPanel.style.display === 'none' ? 'block' : 'none';
                }});
                collapseSettingsBtn.addEventListener('click', () => {{
                    settingsPanel.style.display = 'none';
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
                    <div class="vref">${{vref_html}} <span class="grade">(Grade: ${{verse.grade.toFixed(1)}})</span></div>
                    <div><span class="label">Source:</span> <div>${{verse.source}}</div></div>
                    ${{verse.source_translated ? `<div>(${{verse.source_translated}})</div>` : ''}}
                    <div><span class="label">Translation:</span> <div>${{verse.translation}}</div></div>
                    ${{verse.translation_translated ? `<div>(${{verse.translation_translated}})</div>` : ''}}
                    ${{verse.suggested_translation ? `<div><span class="label">Suggested Translation:</span><div>${{verse.suggested_translation}}</div>${{verse.suggested_translation_translated ? `<div>(${{verse.suggested_translation_translated}})</div>` : ''}}</div>` : ''}}
                    <div><span class="label">Review:</span> <div>${{verse.review}}</div></div>
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

            // 3. Set up UI controls and dynamic content
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
