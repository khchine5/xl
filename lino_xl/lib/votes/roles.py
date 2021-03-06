# Copyright 2016-2017 Luc Saffre
# License: BSD (see file COPYING for details)
"""User roles for this plugin. """

from lino.core.roles import UserRole


class SimpleVotesUser(UserRole):
    """A user who has access to basic contacts functionality.

    """
    
class VotesUser(SimpleVotesUser):
    """A user who has access to full contacts functionality.

    """


class VotesStaff(VotesUser):
    """A user who can configure contacts functionality.

    """

