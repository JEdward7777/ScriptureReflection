# ScriptureReflection: A Project for Reflective Bible Translation

## Overview

**ScriptureReflection** is a research project that explores how AI-driven reflection techniques can aid in generating Bible translations for high-resource languages. The approach leverages a process of iterative improvement through LLM, evaluating translations with an AI grader, and refining them multiple times. While this repository primarily focuses on high-resource languages, many of the techniques used may have applications for low-resource languages as well.

The ultimate goal of the project is not only to produce automated Bible translations but also to develop tools and workflows that complement human involvement in translation and quality assurance.

This repository builds upon the concept of "reflection," first developed in a prior repository, [doctrine_detector](https://github.com/JEdward7777/doctrine_detector). A detailed presentation of the doctrine_detector project can be found [here](https://docs.google.com/presentation/d/1ldMauDWfPkbnybjncj4RQV0xOvcT2sp-XxNjr83wXpQ/edit?usp=sharing).

---

## What is Reflection?

Reflection is a process wherein an LLM generates output, grades its quality, provides feedback, and iteratively refines its output based on that feedback. More specifically:

1. **Initial Output**: an LLM generates content, such as a Bible verse translation.
2. **Grading**: an LLM evaluates that content and assigns a grade with comments on how to improve.
3. **Refinement**: The output is then adjusted based on the feedback.
4. **Iteration**: Steps 2 and 3 are repeated several times, with the goal of improving quality each time.

Initial findings from the doctrine_detector project revealed that multiple parrallel runs of grading improve stability and the reflective improves overall quality as the process cycles.

---

## Goals of the Project
- **Reduce Plagiarism Risk**: Generating translations without verbatim reproduction of known versions.
- **Explore Paraphrasing**: Enable the model to produce translations that balance readability and fidelity.
- **Iterative Improvement**: Utilize iterative reflection to improve translation quality and capture nuances.
- **Grading Metrics**: Investigate ways to quantify and assess grades during the translation process.
- **Human-AI Collaboration**: Build tools for human involvement in the reflection process.

---

## Modules and Project Structure

The repository consists of several modules and YAML configuration files that control various aspects of the pipeline. Each module is tailored to handle a specific phase of the reflection-based translation process. Below is an overview of the key components:

### **1. Initial Draft**
- **`easy_draft.py`**: 
    - Generates an initial draft of translations in JSONL format.
    - Supports creating paraphrases aimed at a specific reading level (e.g., comprehension by a seven-year-old).
- **YAML Config**: `easy_draft.yaml`.

### **2. Rangeable Draft**
- **`rangeable_easy_draft.py`**:
    - Extends `easy_draft.py` by allowing multiple verses to merge into ranges based on natural flow.
    - Useful for paraphrased translations but still requires refinement due to nonsensical merges.
- **YAML Config**: `rangeable_easy_draft.yaml`.

### **3. Input Formats**
- **`input_formats.py`**:
    - Facilitates the import of translations in various formats, including `USFM`, `USX`, and `biblenlp`.
    - Allows specification of both source and target languages, each with their corresponding formats.
    - Requires that the source and target languages adhere to the same versification, preventing incorrect pairings.
- **YAML Config**: `input_formats.yaml`.

### **4. Output Formatting**
- **`output_formats.py`**:
    - Converts the intermediate JSONL outputs into:
      - USFM format
      - JSONL for external tools like [SWARM](https://github.com/ryderwishart/swarm)
      - Markdown for direct viewing on GitHub.
      - A single file report sorted by grade worse to best. If an OpenAi API key is provided it also
        - summarizes the grade comments into a single improvement request and
        - translates everything in the report inline in prenthesis.
    - USFM export may not yet fully support range merging.
- **YAML Config**: `output_formats.yaml`.

### **5. Grading and Reflection**
The reflection process has two main phases:

- **Grading**:
  - **`grade_output.py`**:
    - Assigns grades to translations.
    - Outputs grading results as a separate file.
  - **YAML Config**: `grade_output.yaml`.

- **Single Reflection Cycle**:
  - **`do_reflection.py`**:
    - Applies one round of reflection using grading feedback.
    - Outputs a new translation version.
  - **YAML Config**: `do_reflection.yaml`.

- **Inefficiencies**: Early approaches required manual updates to configurations and resulted in numerous redundant files. To address this, iterative loop-based tools were created.

### **6. Iterative Looping**
- **`grade_reflect_loop.py`**:
    - Automates grading and reflection loops.
    - Enables iterative improvement with dynamic context (adjacent verses).
    - Introduces a mode that focuses on the verse with the lowest grade at each step, propagating improvements while mitigating bad suggestions.
    - The grading-reflection loop is somewhat format-agnostic, allowing use with any JSONL-based verse translation input.

- **Enhancements**:
    - Finalization of challenging verses after several attempts by picking the best version graded so far.
    - Finalization helps resolve alternations on valid but competing outputs (e.g., "deceiver" vs. "false prophet")

- **YAML Config**: `grade_reflect_loop.yaml`.

---

## Findings and Observations

1. **Paraphrasing with Reflection**:
   - Iterative reflection produced a paraphrased version of John 3 ([Output](https://github.com/JEdward7777/ScriptureReflection/blob/main/output/markdown_format/John_3_paraphrase_chapter_reflect_11/JHN/chapter_3.md)).
   - Excessive wordiness emerged before refinement but proved beneficial as it allowed the model to accumulate and refine complex ideas.

2. **Focused Iteration**:
   - Reflection on poorly graded verses improved the consistency of the chapters.
   - Divergent ideas (like adding footnotes) propagated across early drafts and stabilized through consensus.

3. **Challenges**:
   - Stability issues when iterating over full chapters.  Thus the `grade_reflect_loop.py` outputs one verse at a time even though it has a larger context.
   - Oscillation between competing word choices.

4. **Evaluation Metrics**:
   - The average grade of translations improves initially but may plateau or fluctuate without proper safeguards.  Grading from the bottom up prevents oscilations by concentrating on the worst grade.  See the following ([Grade Chart](https://github.com/JEdward7777/ScriptureReflection/blob/main/output/eng_NT_reflected_grade_chart.png)) for the reflection on [Matthew](https://github.com/JEdward7777/ScriptureReflection/blob/main/output/markdown_format/eng_NT_reflected_lowest_grade_first/MAT/chapter_1.md).

---

## Future Development

1. **Human-in-the-Loop Integration**:
   - Create tools for human reviewers to provide feedback on translations.
   - Prototype Streamlit app for collecting verse-specific feedback.

2. **Decoupled Grading and Reflection**:
   - Explore a system where grading serves purely as quality assessment.
   - Enable translators to manually address flagged concerns and re-submit content for additional feedback.


---

## Usage

Each module is configured and executed independently based on YAML files. Below is a general workflow:

1. Generate an initial draft:
   ```bash
   vim easy_draft.yaml
   python easy_draft.py
   ```

2. Grade the translations:
   ```bash
   vim grade_output.yaml
   python grade_output.py
   ```

3. Reflect and iterate:
   ```bash
   vim do_reflection.yaml
   python do_reflection.py
   ```

4. Automate looping:
   ```bash
   vim grade_reflect_loop.yaml
   python grade_reflect_loop.py
   ```

5. Output Formats:
    ```bash
    vim output_formats.yaml
    python output_formats.py
    ```

---

## Examples

- Paraphrased translation of John 3 in English: [Link](https://github.com/JEdward7777/ScriptureReflection/blob/main/output/markdown_format/John_3_1-3_36_reflected_lowest_grade_first/JHN/chapter_3.md)
- Full Book of Matthew in English: [Link](https://github.com/JEdward7777/ScriptureReflection/blob/main/output/markdown_format/eng_NT_reflected_lowest_grade_first/MAT/chapter_1.md)
- Reflection Grade Chart for the Matthew in English: [Link](https://github.com/JEdward7777/ScriptureReflection/blob/main/output/eng_NT_reflected_grade_chart.png)

---

## License

MIT

---

## Contact

For questions or contributions, please reach out to the repository maintainer.