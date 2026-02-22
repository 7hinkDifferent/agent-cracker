"""Sample project: app.py — A simple task manager to be modified by the architect demo."""


class TaskManager:
    def __init__(self):
        self.tasks = []

    def add_task(self, title):
        self.tasks.append({"title": title, "done": False})

    def complete_task(self, index):
        self.tasks[index]["done"] = True

    def list_tasks(self):
        for i, task in enumerate(self.tasks):
            status = "x" if task["done"] else " "
            print(f"[{status}] {i}. {task['title']}")


if __name__ == "__main__":
    tm = TaskManager()
    tm.add_task("Buy groceries")
    tm.add_task("Write report")
    tm.complete_task(0)
    tm.list_tasks()
