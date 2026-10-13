from pathlib import Path
import runpy


def test_lab_example_refresh_preserves_existing_files_and_edits(tmp_path):
    publish = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'docker/publish_examples.py'))['publish']
    source, projects = tmp_path/'source',tmp_path/'projects'
    source.mkdir()
    (source/'demo.py').write_text("print('first')\n")
    (source/'README.md').write_text('Example instructions\n')
    project = projects/'demo'; project.mkdir(parents=True)
    (project/'demo.py').write_text('user project contents\n')
    first, = publish(source,projects)
    assert first.parent == project and (first/'demo.py').read_text() == "print('first')\n"
    (first/'demo.py').write_text('edited example\n')
    assert publish(source,projects) == [first]
    assert (first/'demo.py').read_text() == 'edited example\n'
    (source/'demo.py').write_text("print('second')\n")
    second, = publish(source,projects)
    assert second != first and (second/'demo.py').read_text() == "print('second')\n"
    assert (first/'demo.py').read_text() == 'edited example\n'
    assert (project/'demo.py').read_text() == 'user project contents\n'
