"""
This module contains functions which are used by the output_formats tool.
"""

import os
import yaml

import grade_reflect_loop

def get_config_for( file ):
    """
    Returns the config for the given file for the output_formats tool.
    """
    with open( 'output_formats.yaml', encoding='utf-8' ) as f:
        output_formats_yaml = yaml.load(f, Loader=yaml.FullLoader)
    if os.path.splitext(file)[0] in output_formats_yaml['configs']:
        return output_formats_yaml['configs'][os.path.splitext(file)[0]]
    return None


def get_sorted_verses( translation_data, reference_key, sort_on_first = False ):
    """Returns the next verse as sorted by grades"""
    fake_config_for_grade_reflect_loop = {
        'reference_key': reference_key,
        'grades_per_reflection_loop': float('inf'),
    }

    def get_grade( verse ):
        if sort_on_first:
            reflection_loops = verse.get('reflection_loops', [])
            if reflection_loops:
                first_loop = reflection_loops[0]
                grades = first_loop.get('grades', [])
                if grades:
                    grade = sum( [grade['grade'] for grade in grades] ) / len(grades)
                    return grade
        else:
            grade = grade_reflect_loop.compute_verse_grade( verse, fake_config_for_grade_reflect_loop )
            if grade is not None:
                return grade
        return float('inf')

    sorted_verses = sorted( translation_data, key=get_grade )

    return sorted_verses, get_grade
