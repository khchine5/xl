# -*- coding: UTF-8 -*-
# Copyright 2011-2017 Luc Saffre
# License: BSD (see file COPYING for details)
"""Database models for this plugin.
"""

from lino.api import dd, rt, _
from lino.modlib.users.mixins import Authored
import requests
import json
from django.utils import timezone
from .actions import Import_all_commits, Import_new_commits, Update_all_repos
from lino.mixins import Created
from lino.utils.xmlgen.html import E

class Repository(dd.Model):
    """A **Repository** is a git username and repo name,
    along with an o-auth token to allow for more then 60 requests to
    github an hour

    .. attribute:: user_name

        Github username.

    .. attribute:: repo_name

        Name of Repo belonging to user_name

    .. attribute:: o_auth

        Access token to be used with github's api,
        https://github.com/settings/tokens/new
        For public repos create a token with no scope.
        For private repos the token must have repo commit access,
        because github doesn't provide a way for a token to have
        read only status, we recommend not using this module with
        private repos unless you are sure that the token is secure.

    """

    class Meta:
        app_label = 'github'
        verbose_name = _("Repository")
        verbose_name_plural = _('Repositories')
        abstract = dd.is_abstract_model(__name__, 'Repository')

    user_name = dd.CharField(_("User Name"),
                             max_length=39)
    repo_name = dd.CharField(_("Repository Name"),
                             max_length=100)
    o_auth    = dd.CharField(_("OAuth Token"),
                             max_length=40,
                             blank=True)

    import_all_commits = Import_all_commits()
    import_new_commits = Import_new_commits()
    update_all_repos = Update_all_repos()

    def __str__(self):
        return "%s:%s"%(self.user_name, self.repo_name)

    @dd.displayfield(_("Url"))
    def url(self, ar):
        return "https://github.com/%s/%s/"%(self.user_name,
                                            self.repo_name)

    def api_url(self):
        return "https://api.github.com/repos/%s/%s/" % (self.user_name,
                                                        self.repo_name)

    @dd.displayfield(_("Number Of commits"))
    def size(self, ar):
        return self.commits.count()

    def github_api_get_all_comments(self, sha=None):
        """

        :return: yields json commits of comments for this repo's master branch untill none are left
        """
        parms = {
            'page':1,
            'per_page':100
        }
        if self.o_auth:
            parms['access_token'] = self.o_auth

        if sha is not None:

            parms['sha'] = sha
        r = requests.get(self.api_url() + 'commits', parms)
        content = json.loads(r.content)
        for c in content:
            yield c
        while 'rel="next"' in r.headers.get('link', ""):
            parms['page'] += 1
            r = requests.get(self.api_url() + 'commits', parms)
            content = json.loads(r.content)
            for c in content:
                yield c

    def get_overview_elems(self, ar):
        return [E.a(self.repo_name, href=self.url)]


class Commit(Created, Authored):
    """A **Commit** is a git commit sha and other relevant data.

    .. attribute:: url

        Url pointing to the details for this commit on Github.

    .. attribute:: git_user

        The Github user who commited this commit.
        If there is a user who was linked to this commit via
        user.User.github_username this will be blank.

        Otherwise it will contain the username of the unknown commiter

    .. attribute:: user

        User who commited this commit to github, uses user.User.github_username

    .. attribute:: sha

        Primary Key
        40 Character sha1 hash for the commit

    .. attribute:: summary

        The summary of the commit.
    """

    class Meta:
        app_label = 'github'
        verbose_name = _("Commit")
        verbose_name_plural = _('Commits')
        abstract = dd.is_abstract_model(__name__, 'Commit')


    repository = dd.ForeignKey(Repository,
                               verbose_name=_("Repository"),
                               related_name="commits")

    user = dd.ForeignKey(
        'users.User',
        verbose_name=_("Author"),
        related_name="%(app_label)s_%(class)s_set_by_user",
        blank=True, null=True)
    ticket = dd.ForeignKey(
        'tickets.Ticket',
        verbose_name=_("Ticket"),
        related_name="Commits",
        blank=True, null=True)

    git_user = dd.CharField(_("Github User Name"),
                            blank=True,
                            max_length=39,
                            editable=False)
    commiter_name = dd.CharField(_("Git User Name"),
                            blank=True,
                            max_length=100,)
    sha = dd.CharField(_("Sha Hash"),
                       max_length=40,
                       primary_key=True, #Causes Issues with extjs6
                       unique=True,
                       editable=False)
    url = dd.models.URLField(_("Commit page"),
                       max_length=255,
                       editable=False)
    description = dd.models.TextField(_("Description"),
                               editable=False,
                               blank=True, null=True,
                                   )
    summary = dd.CharField(_("Summary"),
                               editable=False,
                               blank=True, null=True,
                           max_length=100)
    comment = dd.CharField(_("Comment"),
                           blank=True, null=True,
                           max_length=255)

    unassignable = dd.models.BooleanField(_("Unassignable"),
                                       default=False,
                                       editable=True)
    data = dd.models.TextField(_("Raw json") )

    def get_overview_elems(self, ar):
        return [E.a(self.sha, href=self.url)]

    # @dd.displayfield(_("GH diff"))
    # def clickable_url(self, obj, ar):
    #     return E.a(self.sha, href=self.url)



    @classmethod
    def from_api(cls, d, repo):
        """
        :param d: dict representing the commit from the api
        :param repo: repo which this commit is from
        :return: Commit instance, without doing session lookup, just parses json return values and returns instance.
        """
        try:
            c = Commit.objects.get(sha = d['sha'])
            id = c.id
        except Commit.DoesNotExist:
            id = None

        params = dict(
            # id = id,
            repository=repo,
            user=None,
            ticket=None,
            git_user=d['committer']['login'] if d['committer'] is not None else "",
            commiter_name=d['commit']['committer']['name'],
            sha=d['sha'],
            url=d['html_url'],
            created=timezone.utc.localize(timezone.datetime.strptime(d['commit']['committer']['date'], "%Y-%m-%dT%H:%M:%SZ")),
            description=d['commit']['message'],
            summary=d['commit']['message'].split('\n',1)[0][0:100],
            comment="",
            data=json.dumps(d),
            unassignable=False,
        )
        return cls(**params)



dd.inject_field(
    "users.User", 'github_username',
    dd.CharField(_("Github Username"), max_length=39, blank=True))

@dd.schedule_often(3600)
def update_all_repos():
    Repository.update_all_repos.run_from_code(rt.actors.github.Repositories.request())
