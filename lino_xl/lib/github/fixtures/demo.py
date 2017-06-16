from lino.api import rt

def objects():
    Repo = rt.models.github.Repository

    noi = Repo(user_name='lino-framework',
               repo_name='noi')

    ses = rt.login('robin')

    yield noi
    noi.import_all_commits(ses, sha = '8bac51399644261ce1a216a299a1dd3aa5c63632')
