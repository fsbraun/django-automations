from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class TestGroup(models.Model):
    name = models.CharField(_("Test Group Name"), max_length=100)

    class Meta:
        verbose_name = _("test group")
        verbose_name_plural = _("test groups")


class TestUser(AbstractBaseUser):
    username = models.CharField(_("Test User Username"), max_length=100)
    email = models.EmailField(_("email address"), unique=True)
    group = models.ForeignKey(
        TestGroup,
        related_name="test_users",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    is_staff = models.BooleanField(
        _("superuser status"),
        default=False,
    )
    is_superuser = models.BooleanField(
        _("superuser status"),
        default=False,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def has_perm(self, perm, obj=None):
        return True

    def has_perms(self, perm_list, obj=None):
        return True

    def has_module_perms(self, app_label):
        return False

    class Meta:
        verbose_name = _("test user")
        verbose_name_plural = _("test users")


class TestPermission(models.Model):
    slug = models.SlugField(_("Test Permission Slug"), max_length=100)
    groups = models.ManyToManyField(
        TestGroup,
        related_name="test_permissions",
    )

    class Meta:
        verbose_name = _("test permission")
        verbose_name_plural = _("test permissions")
