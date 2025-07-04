from collections import defaultdict
import os
import time
import json
import colorsys
from datetime import datetime
import math

from pydantic import BaseModel
import yaml
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Spacer, Paragraph, PageBreak, HRFlowable, Flowable # pylint: disable=E0401
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT,TA_CENTER
from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.platypus import Table, TableStyle
from openai import OpenAI

from format_utilities import get_config_for, get_sorted_verses
import utils



def translate_verse_report( client, raw_report, config, to_language=None ):

    saw_increase_in_parenthesis = True
    loop_count = 0

    while saw_increase_in_parenthesis:
        print( ".", end='' )


        if to_language is None:
            to_language = config.get("report language", "English")

        system_message = f"You are a translator working in a Conservative Christian context. Your task is to add translations into {to_language} after any text that is not in {to_language}. Only add translations into {to_language}, and do not change anything else. Do not translate into any language other than {to_language}."

        user_message_array = [
            f"Please review the following content. Wherever you find text in a language other than {to_language}, add a translation into {to_language} in parentheses **immediately after the non-{to_language} text**, only if a {to_language} translation is not already present. ",
            f"Make sure to also translate any short quotes in the summary that are not in {to_language}. ",
            f"Only add translations into {to_language}. Do not add or include translations into any other language. ",
            "\n\n**content**:\n```\n",
            raw_report,
            "\n```\n"
        ]

        class TranslationResponse(BaseModel):
            updated_content: str

        completion = utils.use_model( client,
            model=config.get('model', "gpt-4o-mini" ),
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": "".join(str(s) for s in user_message_array)}
            ],
            temperature=config.get('temperature', 1.2),
            top_p=config.get('top_p', 0.9),
            response_format=TranslationResponse
        )

        model_dump = completion.choices[0].message.parsed.model_dump()
        result = model_dump['updated_content']

        old_num_parentheses = raw_report.count('(')
        new_num_parentheses = result.count('(')

        if new_num_parentheses > old_num_parentheses:
            raw_report = result
            saw_increase_in_parenthesis = True
            loop_count += 1
        else:
            saw_increase_in_parenthesis = False

        if loop_count > 7:
            print( f"Stopping adding translations after {loop_count} loops." )
            break
    print()
    return result

def summarize_verse_report( client, raw_report, config, just_summarize=False, no_label=False, output_in_markdown=True, to_language=None ):
    system_message = "You are translation consultant, who is compiling correction for review from " + \
        "a Conservative Christian perspective."

    if not to_language:
        to_language = config.get("report language", "English")

    user_message_array = []

    if not just_summarize:
        user_message_array += [ "The following report was generated for a translated verse of the Bible.\n",
        "Please modify the report so that it is easier to review by the translators who speak ", to_language, ".\n",
        "Provide a reference translation in ", to_language, 
        " for every string which is in another language.  Add it in parrenthesis after the content being translated.\n",
        "Combine the multiple reviewed into a single review in ", to_language, " combining the essence of the individual reviews.\n"
        "Don't add any new content to the report, except for translations and summerizations.  Make sure not to change any of the **Source** or **Translation** text. ",]
    else:
        user_message_array += [ "The following report was generated for a translated verse of the Bible.\n" ]
        if not no_label:
            user_message_array += ["Copy through the Source and Translation sections without modification.\n" ]
        user_message_array += [
            "Combine the multiple reviewed into a single review in ", to_language, " combining the essence of the individual reviews.\n",
            "Don't add any new content to the report, except for the summerization. ",
        ]

    if no_label:
        user_message_array += [ "Don't put a heading on the summarized report.\n" ]

    if output_in_markdown:
        user_message_array += [ "Output in Markdown.\n" ]

    user_message_array += [
        "\n\n**raw report**:\n"
        "```\n", raw_report, "\n```\n"
    ]

    class SummaryResponse(BaseModel):
        updated_report: str

    completion = utils.use_model( client,
        model=config.get('model', "gpt-4o-mini" ),
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": "".join(str(s) for s in user_message_array)}
        ],
        temperature=config.get('temperature', 1.2),
        top_p=config.get('top_p', 0.9),
        response_format=SummaryResponse
    )

    model_dump = completion.choices[0].message.parsed.model_dump()
    result = model_dump['updated_report']

    return result


def get_literal_translation( client, config, text, from_language, to_language ):
    if from_language == to_language: return text

    if not to_language: raise ValueError("to_language is required")
    if not client: raise ValueError("client is required")

    system_message = "You are a translation consultant, drafting literal translations for a Conservative Christian perspective."
    user_message_array = []
    user_message_array += [ "Translate the following text " ]
    if from_language:
        user_message_array += [ "from ", from_language, " " ]
    user_message_array += [ "into ", to_language, "\n" ]

    user_message_array += [ json.dumps({
        "text": text,
    }, ensure_ascii=False) ]

    user_message = "".join(str(x) for x in user_message_array)


    class TranslateResponse(BaseModel):
        literal_translation: str

    completion = utils.use_model( client,
        model=config.get( 'model', 'gpt-4o-mini' ),
        messages=[
            { "role": "system", "content": system_message },
            { "role": "user", "content": user_message }
        ],
        temperature=config.get('temperature', 1.2),
        top_p=config.get('top_p', 0.9),
        response_format=TranslateResponse
    )

    model_dump = completion.choices[0].message.parsed.model_dump()
    literal_translation = model_dump['literal_translation']

    return literal_translation




def grade_to_color(grade, min_grade, max_grade):
    """
    Convert a grade to a color between blue (low) and red (high).
    
    Args:
        grade: The grade value
        min_grade: Minimum grade (will be blue)
        max_grade: Maximum grade (will be red)
    
    Returns:
        Color object
    """
    if max_grade == min_grade:
        # All grades are the same, use neutral color
        return Color(0.5, 0.5, 0.5)
    
    # Normalize grade to 0-1 range
    normalized = (grade - min_grade) / (max_grade - min_grade)
    
    # Create color gradient from blue to red
    # Blue: hue=240°, Red: hue=0°
    # We'll interpolate in HSV space for better color transition
    hue = (1 - normalized) * 240 / 360  # 240° to 0° (blue to red)
    saturation = 0.8
    value = 0.9
    
    # Convert HSV to RGB
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
    
    return Color(r, g, b)

# Add this to your existing PDF generation code, after the title page and before the verses:

def add_heat_map_to_story(story, verses, config, r_get_label, r_get_grade, r_get_ref, r_get_href, header_style, body_text_style, cell_text_style):
    """
    Add heat map section to the PDF story.
    
    Args:
        story: The PDF story list to append to
        verses: List of all verses
        config: Configuration dictionary
    """
    # Add heat map title
    story.append(Paragraph(f"{r_get_label('Grade Heat Map')}", header_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Add legend
    story.append(Paragraph(f"{r_get_label('Blue: Low grades, Red: High grades')}", body_text_style))
    story.append(Spacer(1, 0.1*inch))
    
    # Create and add heat map table
    heat_map_table = create_heat_map_table(verses, config, r_get_grade=r_get_grade, r_get_ref=r_get_ref, r_get_href=r_get_href, cell_text_style=cell_text_style)
    if heat_map_table:
        story.append(heat_map_table)
        story.append(Spacer(1, 0.3*inch))
        story.append(PageBreak())





class BookmarkFlowable(Flowable):
    """A flowable that adds a bookmark at its position"""
    def __init__(self, title, key, level=0):
        self.title = title
        self.key = key
        self.level = level
        Flowable.__init__(self)
    
    def draw(self):
        # This gets called when the flowable is drawn
        canvas = self.canv
        canvas.bookmarkPage(self.key)
        canvas.addOutlineEntry(self.title, self.key, self.level)
    
    def wrap(self, availWidth, availHeight):
        # This flowable takes no space
        return (0, 0)



def create_heat_map_table(verses, config, r_get_grade, r_get_ref, r_get_href, cell_text_style):
    """
    Create a heat map table for verses organized by book and chapter.
    
    Args:
        verses: List of verse objects
        config: Configuration dict that may contain 'low_grade', 'high_grade', and 'wrap_number'
    
    Returns:
        Table object for the PDF
    """
    
    # Get wrap number from config
    wrap_number = config.get('wrap_number', 25)
    
    # Get all grades to determine min/max
    all_grades = [r_get_grade(verse) for verse in verses]
    
    # Determine grade range
    if config and 'low_grade' in config and 'high_grade' in config:
        min_grade = config['low_grade']
        max_grade = config['high_grade']
    else:
        min_grade = min(all_grades)
        max_grade = max(all_grades)

    # Organize verses by book and chapter
    book_chapter_verses = {}
    for verse in verses:
        ref = r_get_ref(verse)
        book, chapter, verse_start, verse_end = utils.split_ref2(ref)

        if book not in book_chapter_verses:
            book_chapter_verses[book] = {}
        if chapter not in book_chapter_verses[book]:
            book_chapter_verses[book][chapter] = []

        book_chapter_verses[book][chapter].append(verse)

    # Initialize style commands
    style_commands = [
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),  # Right align book/chapter labels
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),  # Center align verse squares
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        # Make squares smaller by reducing cell width and height
        ('COLWIDTH', (1, 0), (-1, -1), 12),  # Reduce column width for verse squares
        ('ROWHEIGHT', (0, 0), (-1, -1), 12),  # Reduce row height for all rows

        ('LEFTPADDING', (1, 0), (-1, -1), 1),   # Minimal left padding for verse cells
        ('RIGHTPADDING', (1, 0), (-1, -1), 1),  # Minimal right padding for verse cells
        ('TOPPADDING', (0, 0), (-1, -1), 1),    # Minimal top padding
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1), # Minimal bottom padding
    ]


    # Create table data
    table_data = []

    for book in sorted(book_chapter_verses.keys()):
        for chapter in sorted(book_chapter_verses[book].keys()):
            # Sort verses by verse number
            chapter_verses = book_chapter_verses[book][chapter]
            chapter_verses.sort(key=lambda v: utils.split_ref2(r_get_ref(v))[2])  # Sort by verse_start

            # Split verses into chunks based on wrap_number
            verse_chunks = []
            for i in range(0, len(chapter_verses), wrap_number):
                verse_chunks.append(chapter_verses[i:i + wrap_number])

            # Create a row for each chunk
            for chunk_idx, verse_chunk in enumerate(verse_chunks):
                row_idx = len(table_data)  # Current row index

                # For first chunk, use "Book Chapter", for subsequent use empty or continuation indicator
                if chunk_idx == 0:
                    row_label = f"{book} {chapter}"
                else:
                    row_label = "  ↳"  # Continuation indicator

                row = [row_label]

                # Create colored squares for each verse and add color styling
                for col_idx, verse in enumerate(verse_chunk, 1):
                    ref = r_get_ref(verse)
                    book_name, chapter_num, verse_start, verse_end = utils.split_ref2(ref)

                    grade = r_get_grade(verse)
                    color = grade_to_color(grade, min_grade, max_grade)

                    # Use verse number as cell content
                    cell_content = Paragraph(f"<link href='#{r_get_href(verse)}' color='#000000'>{str(verse_start)}</link>", cell_text_style)
                    row.append(cell_content)

                    # Add color styling for this cell
                    style_commands.append(
                        ('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), color)
                    )
                
                table_data.append(row)
    
    # Determine maximum number of verses in any chapter for consistent table width
    max_verses = max(len(row) - 1 for row in table_data) if table_data else 0
    
    # Pad shorter rows with empty cells
    for row in table_data:
        while len(row) <= max_verses:
            row.append("")
    
    # Create table
    if table_data:
        table = Table(table_data)
        
        table.setStyle(TableStyle(style_commands))
        return table
    
    return None


# --- Font Registration (Improved with better fallback handling) ---
def register_fonts(config_font_name):
    """Register fonts with proper fallback handling"""
    font_paths = [
        (f"/usr/share/fonts/truetype/dejavu/{config_font_name}.ttf", config_font_name),
        (f"/usr/share/fonts/truetype/dejavu/{config_font_name}-Bold.ttf", f"{config_font_name}-Bold"),
        (f"/usr/share/fonts/truetype/dejavu/{config_font_name}-Oblique.ttf", f"{config_font_name}-Italic"),
        # Alternative paths for different systems
        ("/System/Library/Fonts/Helvetica.ttc", "Helvetica"),  # macOS
        ("C:/Windows/Fonts/arial.ttf", "Arial"),  # Windows
    ]

    registered_fonts = {}

    for font_path, font_name in font_paths:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                registered_fonts[font_name] = True
                print(f"Successfully registered font: {font_name}")
            except Exception as e:
                print(f"Error registering {font_name}: {e}")

    # Register font family if we have the base font
    if "DejaVuSans" in registered_fonts:
        try:
            pdfmetrics.registerFontFamily(
                'DejaVuSans',
                normal='DejaVuSans',
                bold='DejaVuSans-Bold' if 'DejaVuSans-Bold' in registered_fonts else 'DejaVuSans',
                italic='DejaVuSans-Italic' if 'DejaVuSans-Italic' in registered_fonts else 'DejaVuSans',
                boldItalic='DejaVuSans-Bold' if 'DejaVuSans-Bold' in registered_fonts else 'DejaVuSans'
            )
            return 'DejaVuSans', True
        except Exception as e:
            print(f"Error registering font family: {e}")

    print("Using built-in Helvetica font (Greek characters may not render correctly)")
    return 'Helvetica', False



def compute_std_devs(values, num_standard_dev):
    """
    Compute the lower and upper bounds of a list of values, given a number of standard deviations from the mean.

    The lower bound is the minimum value, plus the specified number of standard deviations.
    The upper bound is the maximum value, minus the specified number of standard deviations.

    Parameters
    ----------
    values : list
        A list of numeric values.
    num_standard_dev : float
        The number of standard deviations to calculate the bounds from.

    Returns
    -------
    lower_bound : float
        The lower bound.
    upper_bound : float
        The upper bound.

    Raises
    ------
    ValueError
        If the list of values is empty.
    """

    if not values:
        raise ValueError("No values provided")

    # Calculate mean
    n = len(values)
    mean = sum(values) / n

    # Calculate sample standard deviation (ddof=1)
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std_dev = math.sqrt(variance)

    # Calculate the value at num_standard_dev from the minimum
    min_value = min(values)
    max_value = max(values)
    lower_bound = min_value + num_standard_dev * std_dev
    upper_bound = max_value - num_standard_dev * std_dev

    return lower_bound, upper_bound



def run( file ):
    """
    This export creates a single file markdown export
    of the file with the worse verses at the top,
    and the rest in order further down.
    """
    this_config = get_config_for( file ) or {}

    if not this_config.get( 'reports', {} ).get( 'pdf report enabled', False ):
        print( f"{file} does not have pdf report enabled" )
        return


    config_font_name = this_config.get( 'font_name', 'DejaVuSans' )

    
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

    #now sort stuffs.
    book_to_sorted_verses = { 
        book: get_sorted_verses( verses, reference_key, sort_on_first=report_first_iteration )[0]
        for book, verses in book_to_verses.items()
    }



    #Get the output folder ready.
    base_filename = this_config.get( 'output_file', os.path.splitext(file)[0] )
    output_folder = this_config.get( 'output_folder', f"output/pdf_reports/{base_filename}" )
    os.makedirs( output_folder, exist_ok=True )


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

    @utils.cache_decorator( f"{output_folder}_cache/labels", enabled=client is not None )
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

        return r_get_literal_translation_wrapped( text, from_language, to_language )

    @utils.cache_decorator( f"{output_folder}_cache/literal_translation", enabled=client is not None )
    def r_get_literal_translation_wrapped( text, from_language, to_language ):
        return get_literal_translation( client, this_config, text, from_language, to_language )

    @utils.cache_decorator( f"{output_folder}_cache/summerization", enabled=client is not None )
    def r_run_summary( raw_report, to_language ):
        return summarize_verse_report( client, raw_report, this_config.get( "reports", {} ), just_summarize=True, no_label=True, output_in_markdown=False, to_language=to_language )


    @utils.cache_decorator( f"{output_folder}_cache/parenthesis_translation", enabled=client is not None )
    def r_add_parenthesis_translation( text, to_language ):
        return translate_verse_report( client, text, this_config.get( "reports", {} ), to_language=to_language )

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

    font_name, font_registered = register_fonts(config_font_name)


    styles = getSampleStyleSheet()
    # --- Define Custom Styles ---
    header_style = ParagraphStyle(
        'Header',
        parent=styles['h1'],
        fontName=font_name + '-Bold' if font_registered else font_name,
        fontSize=18,
        spaceAfter=0.2 * inch,
        alignment=TA_CENTER
    )

    sub_header_style = ParagraphStyle(
        'SubHeader',
        parent=styles['h2'],
        fontName=font_name + '-Bold' if font_registered else font_name,
        fontSize=14,  # Smaller than header_style
        spaceAfter=0.2 * inch,
        alignment=TA_CENTER  # Centered alignment
    )


    section_title_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['h2'],
        fontName=font_name + '-Bold' if font_registered else font_name,
        fontSize=14,
        spaceBefore=0.3 * inch,
        spaceAfter=0.1 * inch
    )

    toc_link_style = ParagraphStyle(
        'TOCLink',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=12,
        leading=16,
        leftIndent=0.5 * inch,
        textColor='blue'  # Make links visually distinct
    )

    body_text_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=11,
        leading=14,
        alignment=TA_LEFT
    )

    # cell_text_style = ParagraphStyle(
    #     'BodyText',
    #     parent=styles['Normal'],
    #     fontName=font_name,
    #     fontSize=8,
    #     leading=14,
    #     alignment=TA_LEFT
    # )
    cell_text_style = ParagraphStyle(
        'TableCell',
        parent=body_text_style,
        fontSize=8,
        leading=8,  # Line height same as font size
        leftIndent=0,
        rightIndent=0,
        spaceAfter=0,
        spaceBefore=0,
        alignment=1,  # Center alignment
    )

    greek_source_style = ParagraphStyle(
        'GreekSourceText',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        leading=12,
        leftIndent=0.5 * inch,
        rightIndent=0.5 * inch
    )

    #now we will loop through the book names.
    for book, verses in book_to_sorted_verses.items():

        pdf_name = book if book else base_filename

        pdf_prefix = this_config.get( "pdf_reports", {} ).get( "output_prefix", "")
        if pdf_prefix:
            pdf_name = f"{pdf_prefix}{pdf_name}"

        output_filename = f"{output_folder}/{pdf_name}.pdf"
        doc = SimpleDocTemplate(output_filename, pagesize=letter)

        story = []

        # --- Title Page ---
        title = this_config.get( "pdf_reports", {} ).get( "title", f"{base_filename} {book} Report").format( book=book )
        story.append(Paragraph(title, header_style))
        story.append(Spacer(1, 1 * inch))
        story.append(Paragraph(r_get_label(f"Generated on: {datetime.today().strftime('%B %d, %Y')}"), sub_header_style))
        story.append(Spacer(1, 2 * inch))
        story.append(PageBreak())


        # Add heat map
        heat_map_config = this_config.get( "pdf_reports", {} ).get( "heat_map", {} )
        add_heat_map_to_story(story, verses, config=heat_map_config, r_get_label=r_get_label, r_get_grade=r_get_grade, r_get_ref=r_get_ref, r_get_href=r_get_href, header_style=header_style, body_text_style=body_text_style, cell_text_style=cell_text_style)

        #first thing we do is output a configured number of sd verses which are on the low end.
        if percentage_sorted is not None:
            low_end_verses = []
            sorted_verses = sorted( verses, key=r_get_grade )
            for verse in sorted_verses:
                if len(low_end_verses) < percentage_sorted*len(verses)/100:
                    low_end_verses.append(verse)
                else:
                    break

        else:
            grade_cut_off = compute_std_devs( [ r_get_grade(verse) for verse in verses ], num_sd_to_report )[0]
            low_end_verses = [ verse for verse in verses if r_get_grade(verse) <= grade_cut_off ]


        story.append(Paragraph(f"<b>{r_get_label('Lowest sorted by grade')}</b>", header_style))
        story.append(Spacer(1, 0.2*inch))


        start_time = time.time()

        #now iterate through these veses.
        for verse_i, verse in enumerate(low_end_verses):

            current_time = time.time()
            elapsed_time = current_time - start_time
            # estimated_end_time = len(book_to_verses[book])/(verse_i+1) * elapsed_time + current_time
            
            # Calculate estimated total time needed
            estimated_total_time = len(low_end_verses) / (verse_i + 1) * elapsed_time
            # Estimated end time is start time + total estimated duration
            estimated_end_time = start_time + estimated_total_time

            print( f"Processing low end verse {verse_i+1} of {len(low_end_verses)} - {elapsed_time:.2f} seconds elapsed - estimated {estimated_end_time - current_time:.2f} seconds left, estimated end time {datetime.fromtimestamp(estimated_end_time).strftime('%Y-%m-%d %I:%M:%S %p')}" )



            story.append(Paragraph(f"<u><link href='#{r_get_href(verse)}' color='#FF5500'>{r_get_ref(verse)}</link></u>: <font name=\"{config_font_name}\">({r_get_label('Grade')} {r_get_grade(verse):.1f})</font>", section_title_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(Paragraph(f"<b>{r_get_label('Source')}</b>:", body_text_style))
            if r_get_source(verse):
                story.append(Paragraph(r_get_source(verse), greek_source_style))
                if source_language != report_language:
                    story.append(Paragraph(f"({r_get_literal_translation(r_get_source(verse))})", greek_source_style))
            else:
                story.append(Paragraph(f"<i>{r_get_label('No source')}</i>", greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(Paragraph(f"<b>{r_get_label('Translation')}</b>:", body_text_style))
            story.append(Paragraph(r_get_translation(verse), greek_source_style))
            if not r_translation_is_report_language:
                story.append(Paragraph(f"({r_get_literal_translation(r_get_translation(verse), to_language=report_language)})", greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            if r_get_suggested_translation(verse):
                story.append(Paragraph(f"<b>{r_get_label('Suggested Translation')}</b>:", body_text_style))
                story.append(Paragraph(r_get_suggested_translation(verse), greek_source_style))
                if not r_translation_is_report_language:
                    story.append(Paragraph(f"({r_get_literal_translation(r_get_suggested_translation(verse), to_language=report_language)})", greek_source_style))

            story.append(Paragraph(f"<b>{r_get_label('Review')}</b>:", body_text_style))
            story.append(Paragraph(r_get_review(verse), greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(HRFlowable(width="100%", thickness=1, lineCap='round', color="black", spaceBefore=12, spaceAfter=12, hAlign='CENTER', vAlign='BOTTOM', dash=None))

        #add a header to indicate we are now going through everything in natural order.
        # Add a header indicating the transition to all verses in natural order
        story.append(Paragraph(f"<b>{r_get_label('All Verses in Natural Order')}</b>", header_style))
        story.append(Spacer(1, 0.2*inch))


        chapter_bookmarks = {}

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

            
            book_name,chapter_number = utils.split_ref2( r_get_ref( verse ) )[:2]
            book_chapter = f"{book_name} {chapter_number}"
            if book_chapter not in chapter_bookmarks:
                story.append(BookmarkFlowable(title=book_chapter, key=book_chapter, level=0))
                chapter_bookmarks[book_chapter] = True


            story.append(Paragraph(f"<a name='{r_get_href(verse)}'/><b>{r_get_ref(verse)}</b>: <font name=\"{config_font_name}\">({r_get_label('Grade')} {r_get_grade(verse):.1f})</font>", section_title_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(Paragraph(f"<b>{r_get_label('Source')}</b>:", body_text_style))
            if r_get_source(verse):
                story.append(Paragraph(r_get_source(verse), greek_source_style))
                if source_language != report_language:
                    story.append(Paragraph(f"({r_get_literal_translation(r_get_source(verse))})", greek_source_style))
            else:
                story.append(Paragraph(f"<i>{r_get_label('No source')}</i>", greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(Paragraph(f"<b>{r_get_label('Translation')}</b>:", body_text_style))
            story.append(Paragraph(r_get_translation(verse), greek_source_style))
            if not r_translation_is_report_language:
                story.append(Paragraph(f"({r_get_literal_translation(r_get_translation(verse), to_language=report_language)})", greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            if r_get_suggested_translation(verse):
                story.append(Paragraph(f"<b>{r_get_label('Suggested Translation')}</b>:", body_text_style))
                story.append(Paragraph(r_get_suggested_translation(verse), greek_source_style))
                if not r_translation_is_report_language:
                    story.append(Paragraph(f"({r_get_literal_translation(r_get_suggested_translation(verse), to_language=report_language)})", greek_source_style))

            story.append(Paragraph(f"<b>{r_get_label('Review')}</b>:", body_text_style))
            story.append(Paragraph(r_get_review(verse), greek_source_style))
            story.append(Spacer(1, 0.1*inch))

            story.append(HRFlowable(width="100%", thickness=1, lineCap='round', color="black", spaceBefore=12, spaceAfter=12, hAlign='CENTER', vAlign='BOTTOM', dash=None))

        #now output the story.
        doc.build(story)
