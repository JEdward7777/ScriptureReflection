

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

def to_range(selection, everything):
    parsed_range = []
    current_range = None

    for string_verse in everything:
        verse = parse_single_ref(string_verse)
        verse_is_in = string_verse in selection

        if current_range is None or current_range.inclusive != verse_is_in:
            current_range = BibleReferenceRange(start=verse, end=verse, inclusive=verse_is_in)
            parsed_range.append(current_range)
        else:
            current_range.end = verse

    result_parts = []  # Using a list to gather parts of the result
    for i, range_ in enumerate(parsed_range):
        if not range_.inclusive:
            continue  # Skip excluded ranges

        if result_parts:
            result_parts.append(",")

        hide_start_book = hide_start_chapter = hide_start_verse = False
        hide_end_book = hide_end_chapter = hide_end_verse = False

        # Small context checks
        if i >= 2:
            previous_include = parsed_range[i - 2]
            hide_start_book = range_.start.book == previous_include.end.book
            hide_start_chapter = (
                range_.start.chapter == previous_include.end.chapter and 
                range_.start.chapter == range_.end.chapter
            )

        # Large context checks
        has_whole_book = has_whole_chapter = True
        if i >= 1:
            previous_exclude = parsed_range[i - 1]
            has_whole_book &= previous_exclude.end.book != range_.start.book
            has_whole_chapter &= previous_exclude.end.chapter != range_.start.chapter

        if i < len(parsed_range) - 1:
            next_exclude = parsed_range[i + 1]
            has_whole_book &= next_exclude.start.book != range_.start.book
            has_whole_chapter &= next_exclude.start.chapter != range_.start.chapter

        if has_whole_book:
            hide_start_chapter = hide_start_verse = hide_end_chapter = hide_end_verse = True

        if has_whole_chapter:
            hide_start_verse = hide_end_verse = True

        # Determine if we can skip the range end
        skip_range_end = not (
            (not hide_start_book and not hide_end_book and range_.start.book != range_.end.book) or
            (not hide_start_chapter and not hide_end_chapter and range_.start.chapter != range_.end.chapter) or
            (not hide_start_verse and not hide_end_verse and range_.start.verse != range_.end.verse)
        )

        # Small context for end
        if range_.end.book == range_.start.book:
            hide_end_book = True
            if range_.end.chapter == range_.start.chapter:
                hide_end_chapter = True

        # Construct the range string
        if not hide_start_book:
            result_parts.append(f"{range_.start.book}")
            if not hide_start_chapter:
                result_parts.append(" ")

        if not hide_start_chapter:
            result_parts.append(f"{range_.start.chapter}")
            if not hide_start_verse:
                result_parts.append(":")

        if not hide_start_verse:
            result_parts.append(f"{range_.start.verse}")

        if not skip_range_end:
            result_parts.append("-")

            if not hide_end_book:
                result_parts.append(f"{range_.end.book}")
                if not hide_end_chapter:
                    result_parts.append(" ")

            if not hide_end_chapter:
                result_parts.append(f"{range_.end.chapter}")
                if not hide_end_verse:
                    result_parts.append(":")

            if not hide_end_verse:
                result_parts.append(f"{range_.end.verse}")

    return ''.join(result_parts)  # Join the list into a single string at the end