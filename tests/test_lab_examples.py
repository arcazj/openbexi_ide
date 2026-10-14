from pathlib import Path
import runpy


def test_spell_refresh_backs_up_shipped_file_and_preserves_user_edits(tmp_path):
    root = Path(__file__).resolve().parents[1]
    refresh = runpy.run_path(str(root/'docker/publish_examples.py'))['refresh_spell']
    source, projects = tmp_path/'source', tmp_path/'projects'
    source.mkdir()
    new = (root/'examples/test_spell.py').read_bytes()
    original = (root/'examples/spell_native_data.py').read_bytes()
    (source/'test_spell.py').write_bytes(new)
    demo, durable = projects/'demo', projects/'durable'
    demo.mkdir(parents=True)
    durable.mkdir()
    (demo/'test_spell.py').write_bytes(original)
    (durable/'test_spell.py').write_text('# my procedure\n')
    result = refresh(source, projects)
    assert [row['status'] for row in result['files']] == ['refreshed-shipped-file', 'preserved-edited-file']
    assert (demo/'test_spell.py').read_bytes() == new
    assert next(demo.glob('.test_spell-original-*.py')).read_bytes() == original
    assert (durable/'test_spell.py').read_text() == '# my procedure\n'
    assert refresh(source, projects)['files'][0]['status'] == 'current'


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
