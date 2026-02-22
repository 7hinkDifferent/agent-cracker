"""Sample project: app.py — Main application that ties models and utils together."""

from models import User, Post
from utils import format_date, truncate


def create_user(name: str, email: str) -> User:
    """Create a new user with validation."""
    return User(name=name, email=email)


def create_post(title: str, content: str, author: User) -> Post:
    """Create a new blog post."""
    return Post(title=title, content=content, author=author)


def render_post(post: Post, date: str) -> str:
    """Render a post for display."""
    formatted_date = format_date(date)
    summary = truncate(post.summary(), 50)
    return f"[{formatted_date}] {post.author.display_name}: {post.title}\n{summary}"


def list_posts(posts: list, date: str = "2024-01-15") -> None:
    """Print all posts."""
    for post in posts:
        print(render_post(post, date))
        print("---")


if __name__ == "__main__":
    alice = create_user("alice smith", "alice@example.com")
    post1 = create_post("Hello World", "This is my first blog post!", alice)
    post2 = create_post("Python Tips", "Here are some useful Python tips...", alice)
    list_posts([post1, post2])
