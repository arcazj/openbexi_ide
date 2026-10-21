"""SPELL 2.4.4 presentation colors, independent of toolkit and desktop theme.

Procedure colors were sampled from the default-color table on manual page 38.
Procedure state colors belong to the state badge. Code rows stay white, with
a soft execution cursor and independent item-result colors.
"""

PROCEDURE_COLORS = {
    'UNINIT': '#ffffff', 'UNKNOWN': '#ffffff', 'LOADED': '#e0e0e0',
    'RUNNING': '#b9ffd7', 'WAITING': '#ffffb3', 'PROMPT': '#ffff00',
    'PAUSED': '#e0ffc1', 'ERROR': '#ffb9b9', 'ABORTED': '#ffb9b9',
    'FINISHED': '#dcb9ff', 'RELOADING': '#e1feba', 'INTERRUPTED': '#ffffb3',
}
CURRENT_LINE = '#eaf2ff'
CONTROL_COLOR = '#008000'
MONITOR_COLOR = '#0000ff'
RESULT_COLORS = {'SUCCESS': '#00ff00', 'FAILED': '#ff0000', 'ERROR': '#ff0000',
                 'WARNING': '#ffd166', 'IN PROGRESS': '#ffd166'}


def procedure_color(status):
    state = str(status).upper().split(' (', 1)[0]
    state = {'STARTING': 'LOADED', 'FAILED': 'ERROR', 'ABORTED': 'ABORTED'}.get(state, state)
    return PROCEDURE_COLORS.get(state, PROCEDURE_COLORS['UNKNOWN'])


def result_color(status):
    # Do not color unknown/native command stages as success.
    return RESULT_COLORS.get(str(status).upper().split(' (', 1)[0])
