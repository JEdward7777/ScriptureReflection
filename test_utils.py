import utils

def test_get_changes():
    """
    tests the get_changes function
    """

    dict_1 = {
        'a': 1,
        'b': 2,
        'c': {'x': 3, 'y': 4}
    }
    dict_2 = {
        'a': 1,
        'c': {'x': 3, 'y': 5},
        'd': 6
    }
    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['delete', ['b']],
        ['update', ['c', 'y'], 5],
        ['add', ['d'], 6]
    ]

    dict_1 = {
        'a': 1,
        'b': 2,
        'c': {'x': 3, 'y': 4}
    }
    dict_2 = {
        'a': 1,
        'b': 2,
        'c': {'x': 3, 'y': 4}
    }
    changes = utils.get_changes(dict_1, dict_2)
    assert changes == []

    dict_1 = {
        'a': 1,
        'b': 2,
        'c': {'x': 3, 'y': 4}
    }
    dict_2 = {
        'a': 1,
        'b': 2
    }
    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['delete', ['c']]
    ]

    dict_1 = {
        'a': 1,
        'b': 2,
        'c': {'x': 3, 'y': 4}
    }
    dict_2 = {
        'a': 1,
        'b': 2,
        'c': {'x': 3}
    }
    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['delete', ['c', 'y']]
    ]

    dict_1 = {
        'a': 1,
        'b': 2,
        'c': {'x': 3, 'y': 4}
    }
    dict_2 = {
    }
    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['delete', ['a']],
        ['delete', ['b']],
        ['delete', ['c']]
    ]

    dict_1 = {
        'a': 1,
        'b': 2,
        'c': {'d': 3, 'e': {'f': 4, 'g': 5}}
    }
    dict_2 = {
        'a': 1,
        'b': 2,
        'c': {'d': 3, 'e': {'f': 5, 'h': 5}}
    }
    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['update', ['c', 'e', 'f'], 5],
        ['delete', ['c', 'e', 'g']],
        ['add', ['c', 'e', 'h'], 5],
    ]




    dict_1 = {
        'a': 1,
        'b': 2,
    }
    dict_2 = {
        'a': 1,
        'b': 2,
        'c': {'x': 3, 'y': 4}
    }
    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['add', ['c', 'x'], 3],
        ['add', ['c', 'y'], 4]
    ]


    dict_1 = {
        'a': [1,2,3],
        'b': 2,
    }
    dict_2 = {
        'a': [1,2],
        'b': 2,
    }
    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['delete', ['a', 2]],
    ]


    dict_1 = {
        'a': [1],
        'b': 2,
    }
    dict_2 = {
        'a': [],
        'b': 2,
    }
    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['delete', ['a', 0]],
    ]

    dict_1 = {
        'a': [1,2],
        'b': 2,
    }
    dict_2 = {
        'a': [1,2,4],
        'b': 2,
    }

    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['add', ['a', 2], 4],
    ]
    
    dict_1 = {
        'a': [1,2],
        'b': 2,
    }
    dict_2 = {
        'b': 2,
    }

    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['delete', ['a']],
    ]
    
    dict_1 = {
        'b': 2,
    }
    dict_2 = {
        'a': [1,2],
        'b': 2,
    }

    changes = utils.get_changes(dict_1, dict_2)
    assert changes == [
        ['touch_array', ['a']],
        ['add', ['a', 0], 1],
        ['add', ['a', 1], 2],
    ]





def test_apply_changes():
    dict_1 = {
        'a': 1,
        'b': 2,
        'c': {'x': 3, 'y': 4}
    }
    changes = [
        ['delete', ['b']],
        ['update', ['c', 'y'], 5],
        ['add', ['d'], 6]
    ]
    dict_2 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_2 == {
        'a': 1,
        'c': {'x': 3, 'y': 5},
        'd': 6,
    }

    dict_1 = {}
    dict_2 = {'a': 1}
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2


    dict_2 = {'b': 1}
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': {'x': 3, 'y': 4}
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': {'x': 3}
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': {'x': 3}
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': {}
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': 1, 'b': {'e': 2, 'f': 3} }
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': 1, 'b': {'e': 0, 'f': 3} }
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': 1, 'b': {'e': 0, 'f': 3, 'g': { 'h': 4 }} }
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': 1, 'b': 2 }
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': 1, 'b': {'e': 0, 'f': 3, 'g': { 'h': 4 }} }
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': 1, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} }
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} }
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': [ 1, 2, 3 ]
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': [ 1, 3, 3 ]
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': [ 3, 3 ]
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': [ ]
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': 3
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': []
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': [ 1 ]
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': [ 1, 3 ]
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': [ 1, 3, { 'a': 1, 'b': 2 } ]
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2

    dict_2 = {
        'b': 1,
        'c': { 'a': { 'x': { 'y': 1 }}, 'b': {'e': 0, 'f': 2, 'g': { 'h': 4 }} },
        'd': [ 1, 3, { 'a': 1, 'b': 2 } ],
        'e': [ [ 1, 2, 3 ], [ 4, 5, 6 ] ]
    }
    changes = utils.get_changes(dict_1, dict_2)
    dict_1 = utils.apply_changes(dict_1.copy(), changes)
    assert dict_1 == dict_2



