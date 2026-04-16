from __future__ import annotations

from cron_delivery import CronJob, CronRunner


def fake_agent_run(prompt: str, skills: list[str]) -> str:
    if skills:
        return f"ran prompt={prompt!r} with skills={', '.join(skills)}"
    return f"ran prompt={prompt!r} with no extra skills"


def main():
    runner = CronRunner(fake_agent_run)
    job = CronJob(
        job_id="nightly-digest",
        schedule="0 8 * * *",
        prompt="Summarize the last 24h of activity and send a digest.",
        delivery_platform="telegram",
        delivery_target="owner-thread",
        injected_skills=["incident-triage", "python-workflow"],
    )

    print("=" * 72)
    print("Hermes Cron Delivery Demo")
    print("=" * 72)
    print(runner.execute(job))


if __name__ == "__main__":
    main()
