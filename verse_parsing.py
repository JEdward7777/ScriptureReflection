

class BibleReference(object):
    def __init__( self, book, chapter, verse ):
        self.book = book
        self.chapter = chapter
        self.verse = verse

    def __repr__( self ):
        return f"{self.book} {self.chapter}:{self.verse}"

    def __eq__( self, other ):
        return self.book == other.book and self.chapter == other.chapter and self.verse == other.verse

def parse_single_ref( ref ):
    last_space = ref.rfind( ' ' )
    book = ref[:last_space]
    chapter,verse = ref[last_space+1:].split( ':' )
    return BibleReference( book, chapter, verse )

class BibleReferenceRange(object):
    def __init__( self, start, end, inclusive ):
        self.start = start
        self.end = end
        self.inclusive = inclusive

    def __repr__( self ):
        return f"{self.start} to {self.end} (inclusive={self.inclusive})"

def to_range( selection, everything ):
    parsed_range = []
    current_range = None
    for string_verse in everything:
        verse = parse_single_ref(string_verse)
        verse_is_in = string_verse in selection
        if current_range is None or current_range.inclusive != verse_is_in:
            current_range = BibleReferenceRange( start=verse, end=verse, inclusive=verse_is_in )
            parsed_range.append( current_range )
        else:
            current_range.end = verse

    result_string = ""
    for i, range_ in enumerate(parsed_range):
        if range_.inclusive:
            if result_string: result_string += ","

            hide_start_book = False
            hide_start_chapter = False
            hide_start_verse = False
            hide_end_book = False
            hide_end_chapter = False
            hide_end_verse = False

            #for the small context see if we are within the context of the previous
            #included range.
            if i >= 2:
                previous_include = parsed_range[i-2]
                if range_.start.book == previous_include.end.book: hide_start_book = True
                if range_.start.chapter == previous_include.end.chapter: hide_start_chapter = True
            
            #for the large context see if we contain a whole book or chapter
            #so that we don't need to list the chapters or verses.
            has_whole_book = True
            has_whole_chapter = True
            if i >= 1:
                previous_exclude = parsed_range[i-1]
                if previous_exclude.end.book == range_.start.book:
                    has_whole_book = False
                if previous_exclude.end.chapter == range_.start.chapter:
                    has_whole_chapter = False
            if i < len(parsed_range)-1:
                next_exclude = parsed_range[i+1]
                if next_exclude.start.book == range_.start.book:
                    has_whole_book = False
                if next_exclude.start.chapter == range_.start.chapter:
                    has_whole_chapter = False
            if has_whole_book:
                hide_start_chapter = True
                hide_start_verse = True
                hide_end_chapter = True
                hide_end_verse = True
            if has_whole_chapter:
                hide_start_verse = True
                hide_end_verse = True

            #if the end of the range is the same as the start for what is visible
            #then we need to skip the end entirely.
            skip_range_end = True
            if not hide_start_book and not hide_end_book and range_.start.book != range_.end.book:
                skip_range_end = False
            if not hide_start_chapter and not hide_end_chapter and range_.start.chapter != range_.end.chapter:
                skip_range_end = False
            if not hide_start_verse and not hide_end_verse and range_.start.verse != range_.end.verse:
                skip_range_end = False

            #for the small context again see if the end is within context of the start.
            if range_.end.book == range_.start.book:
                hide_end_book = True
                if range_.end.chapter == range_.start.chapter:
                    hide_end_chapter = True

            if not hide_start_book:
                result_string += f"{range_.start.book}"
                if not hide_start_chapter:
                    result_string += " "

            if not hide_start_chapter:
                result_string += f"{range_.start.chapter}"
                if not hide_start_verse:
                    result_string += ":"

            if not hide_start_verse:
                result_string += f"{range_.start.verse}"


            if not skip_range_end:
                result_string += "-"

                if not hide_end_book:
                    result_string += f"{range_.end.book}"
                    if not hide_end_chapter:
                        result_string += " "
                
                if not hide_end_chapter:
                    result_string += f"{range_.end.chapter}"
                    if not hide_end_verse:
                        result_string += ":"
                
                if not hide_end_verse:
                    result_string += f"{range_.end.verse}"
    return result_string