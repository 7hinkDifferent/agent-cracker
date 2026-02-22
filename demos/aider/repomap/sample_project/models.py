"""Sample project: models.py — Data models used by the app."""

from dataclasses import dataclass
from utils import validate_email, slugify


@dataclass
class User:
    name: str
    email: str

    def __post_init__(self):
        if not validate_email(self.email):
            raise ValueError(f"Invalid email: {self.email}")

    @property
    def display_name(self):
        return self.name.title()


@dataclass
class Post:
    title: str
    content: str
    author: User

    @property
    def slug(self):
        return slugify(self.title)

    def summary(self, max_length=100):
        if len(self.content) <= max_length:
            return self.content
        return self.content[:max_length] + "..."
