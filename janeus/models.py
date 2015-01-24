from django.db import models
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from janeus import Janeus


class JaneusRole(models.Model):
    role = models.CharField(max_length=250)
    groups = models.ManyToManyField(Group, blank=True)
    permissions = models.ManyToManyField(Permission, blank=True)

    def __unicode__(self):
        return unicode(u"Role '{0}'".format(self.role))

    @staticmethod
    def reset(user):
        user.groups.clear()
        user.user_permissions.clear()

    def apply(self, user):
        user.groups.add(*self.groups.all())
        user.user_permissions.add(*self.permissions.all())


class JaneusUser(models.Model):
    uid = models.CharField(max_length=250, unique=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE)

    def __unicode__(self):
        return unicode(u"Janeus User '{0}'".format(self.uid))

    def reset_from_ldap(self, attrs=None, roles=None):
        assert self.user is not None
        assert self.pk is not None

        # retrieve attrs and groups if necessary
        if attrs is None or roles is None:
            res = Janeus().by_uid(self.uid)
            if res is None:
                self.user.delete()  # cascades
                return None
            dn, attrs = res
            if roles is None:
                groups = Janeus().groups_of_dn(dn)
                roles = JaneusRole.objects.filter(role__in=groups)

        # check if user has access
        if len(roles) == 0:
            self.user.delete()  # cascades
            return None

        # set attributes
        setattr(self.user, 'last_name', attrs['sn'][0])
        setattr(self.user, 'email', attrs['mail'][0])
        setattr(self.user, 'is_active', True)
        setattr(self.user, 'is_staff', True)

        # set groups and permissions
        JaneusRole.reset(self.user)
        for r in roles:
            r.apply(self.user)

        # save user
        self.user.save()
        return self.user
