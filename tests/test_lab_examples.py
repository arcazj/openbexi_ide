from pathlib import Path
import runpy

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1]/'docker/publish_examples.py'))


def test_upgrade_preserves_contents_and_restart_keeps_user_edits(tmp_path):
    source, projects = tmp_path/'source', tmp_path/'projects'
    source.mkdir()
    (source/'hello.py').write_text('new shipped version\n')
    project = projects/'demo'
    project.mkdir(parents=True)
    (project/'hello.py').write_text('my edited hello\n')
    (project/'private.py').write_text('my private procedure\n')
    first, = MODULE['publish'](source, projects)
    assert (project/first['preserved'][0]).read_text() == 'my edited hello\n'
    assert (project/'hello.py').read_text() == 'new shipped version\n'
    (project/'hello.py').write_text('new user edit\n')
    again, = MODULE['publish'](source, projects)
    assert again['kept_edits'] == ['hello.py'] and not again['installed']
    assert (project/'hello.py').read_text() == 'new user edit\n'
    assert (project/'private.py').read_text() == 'my private procedure\n'
    (source/'hello.py').write_text('next shipped version\n')
    updated, = MODULE['publish'](source, projects)
    assert (project/updated['preserved'][0]).read_text() == 'new user edit\n'
    assert (project/'hello.py').read_text() == 'next shipped version\n'


def test_only_verified_generated_folders_are_deleted(tmp_path):
    source, projects = tmp_path/'source', tmp_path/'projects'
    source.mkdir()
    (source/'hello.py').write_text('hello\n')
    project = projects/'demo'
    project.mkdir(parents=True)
    pristine = project/'preparing'
    pristine.mkdir()
    (pristine/'old.py').write_text('old example\n')
    pristine = pristine.rename(project/('examples-'+MODULE['generated_digest'](pristine)))
    changed = project/'examples-000000000000'
    changed.mkdir()
    (changed/'important.py').write_text('user edits\n')
    report, = MODULE['publish'](source, projects)
    assert report['removed_generated'] == [pristine.name]
    assert not pristine.exists() and not changed.exists()
    assert (project/report['preserved'][0]/'important.py').read_text() == 'user edits\n'


def test_retired_root_examples_are_backed_up_not_discarded(tmp_path):
    source, projects = tmp_path/'source', tmp_path/'projects'
    source.mkdir()
    (source/'hello.py').write_text('hello\n')
    project = projects/'demo'
    project.mkdir(parents=True)
    (project/'graphics_demo.py').write_text('modified graphic\n')
    report, = MODULE['publish'](source, projects)
    assert not (project/'graphics_demo.py').exists()
    assert (project/report['preserved'][0]).read_text() == 'modified graphic\n'
