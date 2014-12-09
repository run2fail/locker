
def expand_vars(text, container):
    ''' Expand some variables

    :param text: The string with variables to expand
    :param container: Container instance to access the replacement strings
    :returns: Expanded string
    '''
    text = text.replace('$name', container.name)
    text = text.replace('$project', container.project.name)
    return text