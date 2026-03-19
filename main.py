if __name__ == "__main__":
    import sys
    import logging
    import utils.config
    from agents.agentmesh import run_scan

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s — %(message)s"
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # --now flag: run once immediately and exit (for testing)
    if "--now" in sys.argv:
        print("Running scan now (--now mode)...")
        run_scan()
        print("Scan complete.")
        sys.exit(0)

    # Normal mode: scheduled runs
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    scheduler.add_job(
        run_scan,
        trigger="cron",
        day_of_week="mon-fri",
        hour="9-15",
        minute="0,15,30,45",
        id="market_scan",
        name="Market hours scan",
    )

    scheduler.add_job(
        run_scan,
        trigger="cron",
        day_of_week="mon-fri",
        hour=18,
        minute=30,
        id="deals_scan",
        name="End of day deals scan",
    )

    print("agentmesh started")
    print(f"  market scan : Mon–Fri 9:00am–4:00pm IST every 15 min")
    print(f"  deals scan  : Mon–Fri 6:30pm IST daily")
    print(f"  DRY_RUN     : {utils.config.DRY_RUN}")
    print(f"  next run    : {scheduler.get_jobs()[0].next_run_time}")
    print(f"  tip         : run with --now to trigger a scan immediately")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nagentmesh stopped")
        scheduler.shutdown()
