from verse_parsing import to_range


refs = [
    "GEN 1:1",
    "GEN 1:2",
    "GEN 1:3",
    "GEN 1:4",
    "GEN 2:1",
    "GEN 2:2",
    "GEN 2:3",
    "GEN 3:1",
    "GEN 3:2",
    "GEN 3:3",
    "EXD 1:1",
    "EXD 1:2",
    "EXD 1:3",
    "EXD 2:1",
    "EXD 2:2",
    "EXD 2:3",
]
def test_single():
    assert to_range(["GEN 1:1"], refs) == "GEN 1:1"
def test_single_range():
    assert to_range(["GEN 1:1","GEN 1:2", "GEN 1:3"], refs ) == "GEN 1:1-3"
def test_chapter_range():
    assert to_range( ["GEN 1:1",
    "GEN 1:2",
    "GEN 1:3",
    "GEN 1:4",
    "GEN 2:1",
    "GEN 2:2",
    "GEN 2:3"], refs ) == "GEN 1-2"
def test_verse_list():
    assert to_range(["GEN 1:1", "GEN 1:3"], refs) == "GEN 1:1,3"
def test_chapter_list():
    assert to_range( [
    "GEN 1:1",
    "GEN 1:2",
    "GEN 1:3",
    "GEN 1:4",
    "GEN 3:1",
    "GEN 3:2",
    "GEN 3:3" ], refs ) == "GEN 1,3"

def test_whole_book():
    assert to_range( [
    "GEN 1:1",
    "GEN 1:2",
    "GEN 1:3",
    "GEN 1:4",
    "GEN 2:1",
    "GEN 2:2",
    "GEN 2:3",
    "GEN 3:1",
    "GEN 3:2",
    "GEN 3:3", ], refs ) == "GEN"

def test_book_range():
    test_refs = [
        "GEN 1:1",
        "GEN 1:2",
        "GEN 1:3",
        "GEN 1:4",
        "GEN 2:1",
        "GEN 2:2",
        "GEN 2:3",
        "GEN 3:1",
        "GEN 3:2",
        "GEN 3:3",
        "EXD 1:1",
        "EXD 1:2",
        "EXD 1:3",
        "EXD 2:1",
        "EXD 2:2",
        "EXD 2:3",
    ]
    assert to_range( test_refs, refs ) == "GEN-EXD"

def test_range_and_list():
    test_refs = [
        "GEN 1:1",
        "GEN 1:3",
        "GEN 1:4",
    ]
    assert to_range( test_refs, refs ) == "GEN 1:1,3-4"



def test_not_hide_verse_when_start_showing_verse():
    """
    If the previous range shows a verse, you can't hide the verse
    otherwise it looks like a verse range.
    """
    test_refs = [
        "GEN 1:2",
        "GEN 1:3",
        "GEN 1:4",
        "GEN 2:1",
        "GEN 2:2",
        "GEN 2:3",
        "GEN 3:1",
        "GEN 3:2",
        "GEN 3:3",
    ]
    assert to_range( test_refs, refs ) == "GEN 1:2-3:3"

def test_not_hide_chapter_when_next_verse_is_next_chapter():
    test_refs = [
        "GEN 1:1",
        #"GEN 1:2",
        "GEN 1:3",
        "GEN 1:4",
        "GEN 2:1",
        # "GEN 2:2",
        # "GEN 2:3",
        # "GEN 3:1",
        # "GEN 3:2",
        # "GEN 3:3",
        # "EXD 1:1",
        # "EXD 1:2",
        # "EXD 1:3",
        # "EXD 2:1",
        # "EXD 2:2",
        # "EXD 2:3",    
    ]
    assert to_range( test_refs, refs ) == "GEN 1:1,1:3-2:1"

def test_have_whole_start_chapter_but_not_end_chapter():
    """
    If you have the whole starting chapter but not the whole ending chapter,
    you can't hide the verse on the end of the range because you don't have all 
    the verses.
    """
    test_refs = [
        "GEN 1:1",
        "GEN 1:2",
        "GEN 1:3",
        "GEN 1:4",
        "GEN 2:1",
        # "GEN 2:2",
        "GEN 2:3",
        "GEN 3:1",
        "GEN 3:2",
        "GEN 3:3",
        "EXD 1:1",
        "EXD 1:2",
        "EXD 1:3",
        "EXD 2:1",
        "EXD 2:2",
        "EXD 2:3",    
    ]
    assert to_range( test_refs, refs ) == "GEN 1-2:1,3-EXD"