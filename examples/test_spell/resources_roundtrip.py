"""Write/read typed ground resources through the original driver."""
from spell.lang.functions import Display, GetResource, SetResource
for expected in (0, False, 'hello', [1, 2], {'answer': 42}):
    assert SetResource('value', expected, HandleError=False)
    actual = GetResource('value', HandleError=False)
    assert actual == expected and type(actual) is type(expected)
    Display('Resource round trip: ' + repr(actual))
Display('SPELL_RESOURCES_PASS')
