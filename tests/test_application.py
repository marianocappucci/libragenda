from datetime import date, datetime, time, timedelta, timezone

import pytest

from libragenda import (
    AgendaPolicy,
    Appointment,
    AppointmentConflict,
    AppointmentStatus,
    AppointmentUnavailable,
    Availability,
    Holiday,
    InMemoryScheduler,
    InvalidTransition,
    OverbookingLimitReached,
    RecurrenceRule,
    Resource,
    ResourceBranchMismatch,
    first_time_at,
    generate_occurrences,
)


def make_appointment(identifier="apt-1", hour=10, status=AppointmentStatus.PENDING, branch_id=None):
    return Appointment(identifier, "resource-1", "service-1", "client-1",
                       datetime(2026, 7, 20, hour), timedelta(minutes=45), status,
                       branch_id=branch_id)


@pytest.fixture
def scheduler():
    return InMemoryScheduler([Availability("resource-1", 0, time(9), time(18))])


def test_create_confirm_and_cancel(scheduler):
    created = scheduler.create(make_appointment())
    assert created.status is AppointmentStatus.PENDING
    assert scheduler.confirm(created.id).status is AppointmentStatus.CONFIRMED
    assert scheduler.cancel(created.id).status is AppointmentStatus.CANCELLED


def test_create_rejects_conflict(scheduler):
    scheduler.create(make_appointment("first"))
    with pytest.raises(AppointmentConflict):
        scheduler.create(make_appointment("second"))


def test_create_rejects_unavailable_slot(scheduler):
    with pytest.raises(AppointmentUnavailable):
        scheduler.create(make_appointment(hour=19))


def test_reschedule_validates_new_slot(scheduler):
    scheduler.create(make_appointment())
    moved = scheduler.reschedule("apt-1", datetime(2026, 7, 20, 12))
    assert moved.starts_at.hour == 12


def test_cancelled_appointment_cannot_be_rescheduled_or_confirmed(scheduler):
    scheduler.create(make_appointment())
    scheduler.cancel("apt-1")
    with pytest.raises(InvalidTransition):
        scheduler.reschedule("apt-1", datetime(2026, 7, 20, 12))
    with pytest.raises(InvalidTransition):
        scheduler.confirm("apt-1")


def test_cancel_accepts_an_optional_reason(scheduler):
    scheduler.create(make_appointment())
    cancelled = scheduler.cancel("apt-1", reason="cliente no puede asistir")
    assert cancelled.reason == "cliente no puede asistir"


def test_reschedule_accepts_an_optional_reason_and_preserves_it_if_omitted(scheduler):
    scheduler.create(make_appointment())
    moved = scheduler.reschedule("apt-1", datetime(2026, 7, 20, 12), reason="pidio otro horario")
    assert moved.reason == "pidio otro horario"
    moved_again = scheduler.reschedule("apt-1", datetime(2026, 7, 20, 13))
    assert moved_again.reason == "pidio otro horario"


def test_confirmed_appointment_cannot_be_confirmed_again(scheduler):
    scheduler.create(make_appointment())
    scheduler.confirm("apt-1")
    with pytest.raises(InvalidTransition):
        scheduler.confirm("apt-1")


def test_complete_confirmed_appointment(scheduler):
    scheduler.create(make_appointment())
    scheduler.confirm("apt-1")
    assert scheduler.complete("apt-1").status is AppointmentStatus.COMPLETED


def test_complete_in_progress_appointment(scheduler):
    scheduler.create(make_appointment(status=AppointmentStatus.IN_PROGRESS))
    assert scheduler.complete("apt-1").status is AppointmentStatus.COMPLETED


def test_pending_appointment_cannot_be_completed(scheduler):
    scheduler.create(make_appointment())
    with pytest.raises(InvalidTransition):
        scheduler.complete("apt-1")


def test_completed_appointment_cannot_be_completed_again(scheduler):
    scheduler.create(make_appointment())
    scheduler.confirm("apt-1")
    scheduler.complete("apt-1")
    with pytest.raises(InvalidTransition):
        scheduler.complete("apt-1")


def test_create_rejects_appointment_on_a_branch_holiday():
    scheduler = InMemoryScheduler(
        [Availability("resource-1", 0, time(9), time(18))],
        holidays=[Holiday("branch-1", date(2026, 7, 20), "Feriado")],
        resources=[Resource("resource-1", "Box 1", branch_id="branch-1")],
    )
    with pytest.raises(AppointmentUnavailable):
        scheduler.create(make_appointment())


def test_create_rejects_resource_from_a_different_branch():
    scheduler = InMemoryScheduler(
        [Availability("resource-1", 0, time(9), time(18))],
        resources=[Resource("resource-1", "Box 1", branch_id="branch-2")],
    )
    with pytest.raises(ResourceBranchMismatch):
        scheduler.create(make_appointment(branch_id="branch-1"))


def test_reschedule_preserves_branch_id_and_still_enforces_it():
    scheduler = InMemoryScheduler(
        [Availability("resource-1", 0, time(9), time(18))],
        resources=[Resource("resource-1", "Box 1", branch_id="branch-1")],
    )
    scheduler.create(make_appointment(branch_id="branch-1"))
    moved = scheduler.reschedule("apt-1", datetime(2026, 7, 20, 12))
    assert moved.branch_id == "branch-1"


def _create_series(scheduler: InMemoryScheduler, series_id: str, count: int) -> list[Appointment]:
    rule = RecurrenceRule(weekdays=frozenset({0}), start_time=time(10, 0),
                          starts_on=date(2026, 7, 20), count=count)
    created = []
    for index, occurrence in enumerate(generate_occurrences(rule)):
        appointment = Appointment(
            f"apt-{index}", "resource-1", "service-1", "client-1",
            occurrence, timedelta(minutes=45), series_id=series_id,
        )
        created.append(scheduler.create(appointment))
    return created


def test_list_series_returns_only_matching_occurrences(scheduler):
    _create_series(scheduler, "series-1", count=3)
    scheduler.create(make_appointment("standalone", hour=14))
    assert len(scheduler.list_series("series-1")) == 3


def test_cancel_series_cancels_every_pending_occurrence(scheduler):
    _create_series(scheduler, "series-1", count=3)
    cancelled = scheduler.cancel_series("series-1")
    assert len(cancelled) == 3
    assert all(item.status is AppointmentStatus.CANCELLED for item in cancelled)


def test_cancel_series_applies_the_same_reason_to_every_occurrence(scheduler):
    _create_series(scheduler, "series-1", count=2)
    cancelled = scheduler.cancel_series("series-1", reason="profesional de licencia")
    assert all(item.reason == "profesional de licencia" for item in cancelled)


def test_cancel_series_skips_occurrences_already_closed_out(scheduler):
    occurrences = _create_series(scheduler, "series-1", count=2)
    scheduler.confirm(occurrences[0].id)
    scheduler.cancel(occurrences[0].id)  # already cancelled

    cancelled = scheduler.cancel_series("series-1")

    assert len(cancelled) == 1
    assert cancelled[0].id == occurrences[1].id


# -- start() ----------------------------------------------------------------


def test_start_moves_a_confirmed_appointment_to_in_progress(scheduler):
    scheduler.create(make_appointment())
    scheduler.confirm("apt-1")

    assert scheduler.start("apt-1").status is AppointmentStatus.IN_PROGRESS


def test_start_is_refused_before_the_appointment_is_confirmed(scheduler):
    scheduler.create(make_appointment())

    with pytest.raises(InvalidTransition):
        scheduler.start("apt-1")


def test_a_started_appointment_can_only_be_completed(scheduler):
    scheduler.create(make_appointment())
    scheduler.confirm("apt-1")
    scheduler.start("apt-1")

    with pytest.raises(InvalidTransition):
        scheduler.cancel("apt-1")
    assert scheduler.complete("apt-1").status is AppointmentStatus.COMPLETED


# -- transition history -----------------------------------------------------


class FakeClock:
    """Hands out fixed, increasing instants so the log is assertable."""

    def __init__(self):
        self.now = datetime(2026, 7, 20, 9, tzinfo=timezone.utc)

    def __call__(self):
        self.now += timedelta(minutes=1)
        return self.now


@pytest.fixture
def logged_scheduler():
    return InMemoryScheduler(
        [Availability("resource-1", 0, time(9), time(18))], clock=FakeClock()
    )


def test_creating_an_appointment_is_itself_recorded(logged_scheduler):
    logged_scheduler.create(make_appointment(), actor="recepcion")

    history = logged_scheduler.history("apt-1")

    assert len(history) == 1
    assert history[0].from_status is None
    assert history[0].to_status is AppointmentStatus.PENDING
    assert history[0].actor == "recepcion"


def test_history_records_every_step_in_order(logged_scheduler):
    logged_scheduler.create(make_appointment(), actor="recepcion")
    logged_scheduler.confirm("apt-1", actor="recepcion")
    logged_scheduler.start("apt-1", actor="dr-perez")
    logged_scheduler.complete("apt-1", actor="dr-perez")

    steps = [(item.from_status, item.to_status) for item in logged_scheduler.history("apt-1")]

    assert steps == [
        (None, AppointmentStatus.PENDING),
        (AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED),
        (AppointmentStatus.CONFIRMED, AppointmentStatus.IN_PROGRESS),
        (AppointmentStatus.IN_PROGRESS, AppointmentStatus.COMPLETED),
    ]


def test_attention_times_are_read_from_the_history(logged_scheduler):
    logged_scheduler.create(make_appointment())
    logged_scheduler.confirm("apt-1")
    logged_scheduler.start("apt-1")
    logged_scheduler.complete("apt-1")

    history = logged_scheduler.history("apt-1")
    started = first_time_at(history, AppointmentStatus.IN_PROGRESS)
    finished = first_time_at(history, AppointmentStatus.COMPLETED)

    # The clock ticks a minute per call: started on the 3rd, finished on the
    # 4th. No column on the appointment holds either instant.
    assert finished - started == timedelta(minutes=1)


def test_a_cancellation_records_its_reason_and_actor(logged_scheduler):
    logged_scheduler.create(make_appointment())
    logged_scheduler.cancel("apt-1", reason="el paciente avisó", actor="recepcion")

    last = logged_scheduler.history("apt-1")[-1]

    assert last.to_status is AppointmentStatus.CANCELLED
    assert last.reason == "el paciente avisó"
    assert last.actor == "recepcion"


def test_a_reschedule_is_audited_even_though_the_status_does_not_change(logged_scheduler):
    logged_scheduler.create(make_appointment())
    logged_scheduler.reschedule(
        "apt-1", datetime(2026, 7, 20, 12), reason="pidió más tarde", actor="recepcion"
    )

    last = logged_scheduler.history("apt-1")[-1]

    assert (last.from_status, last.to_status) == (
        AppointmentStatus.PENDING, AppointmentStatus.PENDING,
    )
    assert last.reason == "pidió más tarde"


def test_history_is_per_appointment(logged_scheduler):
    logged_scheduler.create(make_appointment("apt-1"))
    logged_scheduler.create(make_appointment("apt-2", hour=12))

    assert len(logged_scheduler.history("apt-1")) == 1
    assert logged_scheduler.history("apt-3") == []


# -- authorized overbooking -------------------------------------------------


@pytest.fixture
def overbookable():
    return InMemoryScheduler(
        [Availability("resource-1", 0, time(9), time(18))],
        policies=[AgendaPolicy("resource-1", max_overbookings_per_day=1)],
    )


def test_an_overlap_is_still_refused_when_nobody_asked_to_overbook(overbookable):
    overbookable.create(make_appointment("first"))

    with pytest.raises(AppointmentConflict):
        overbookable.create(make_appointment("second"))


def test_an_authorized_overbooking_is_accepted_and_marked(overbookable):
    overbookable.create(make_appointment("first"))

    extra = overbookable.create(make_appointment("second"), allow_overbooking=True)

    assert extra.overbooked is True
    assert overbookable.get("second").overbooked is True


def test_the_cap_stops_the_next_overbooking_of_the_day(overbookable):
    overbookable.create(make_appointment("first"))
    overbookable.create(make_appointment("second"), allow_overbooking=True)

    with pytest.raises(OverbookingLimitReached):
        overbookable.create(make_appointment("third"), allow_overbooking=True)


def test_an_agenda_that_never_opted_in_refuses_overbooking_outright():
    scheduler = InMemoryScheduler([Availability("resource-1", 0, time(9), time(18))])
    scheduler.create(make_appointment("first"))

    with pytest.raises(OverbookingLimitReached):
        scheduler.create(make_appointment("second"), allow_overbooking=True)


def test_asking_to_overbook_without_overlapping_is_an_ordinary_booking(overbookable):
    # Otherwise a permissive caller would burn the day's cap on bookings that
    # never competed with anything.
    booked = overbookable.create(make_appointment("first"), allow_overbooking=True)

    assert booked.overbooked is False


def test_the_cap_counts_only_the_day_it_applies_to(overbookable):
    overbookable.create(make_appointment("first"))
    overbookable.create(make_appointment("second"), allow_overbooking=True)
    # A week later, same weekday and hour: the cap starts over.
    next_monday = Appointment("third", "resource-1", "service-1", "client-1",
                              datetime(2026, 7, 27, 10), timedelta(minutes=45))
    overbookable.create(next_monday)

    fourth = Appointment("fourth", "resource-1", "service-1", "client-1",
                         datetime(2026, 7, 27, 10), timedelta(minutes=45))
    assert overbookable.create(fourth, allow_overbooking=True).overbooked is True


def test_a_cancelled_overbooking_frees_room_under_the_cap(overbookable):
    overbookable.create(make_appointment("first"))
    overbookable.create(make_appointment("second"), allow_overbooking=True)
    overbookable.cancel("second")

    assert overbookable.create(
        make_appointment("third"), allow_overbooking=True
    ).overbooked is True


def test_overbooking_does_not_open_a_closed_agenda(overbookable):
    # It relaxes the conflict rule and nothing else: 19h is outside the window.
    with pytest.raises(AppointmentUnavailable):
        overbookable.create(make_appointment("late", hour=19), allow_overbooking=True)


# -- the agenda gap, through the scheduler ----------------------------------


def test_the_agenda_interval_rejects_a_booking_that_does_not_clear_it():
    scheduler = InMemoryScheduler(
        [Availability("resource-1", 0, time(9), time(18))],
        policies=[AgendaPolicy("resource-1", slot_interval=timedelta(minutes=15))],
    )
    scheduler.create(make_appointment("first", hour=10))

    # The first one ends at 10:45; starting at 10:50 leaves 5 of the 15
    # minutes the policy demands, so it does not fit.
    second = Appointment("second", "resource-1", "service-1", "client-1",
                         datetime(2026, 7, 20, 10, 50), timedelta(minutes=45))
    with pytest.raises(AppointmentConflict):
        scheduler.create(second)


# -- secondary resources, through the scheduler ------------------------------


def test_the_scheduler_refuses_two_professionals_in_one_room():
    scheduler = InMemoryScheduler([
        Availability("doctor-1", 0, time(9), time(18)),
        Availability("doctor-9", 0, time(9), time(18)),
    ])
    scheduler.create(Appointment("first", "doctor-1", "service-1", "client-1",
                                 datetime(2026, 7, 20, 10), timedelta(minutes=45),
                                 secondary_resource_ids=("room-2",)))

    clash = Appointment("second", "doctor-9", "service-1", "client-2",
                        datetime(2026, 7, 20, 10), timedelta(minutes=45),
                        secondary_resource_ids=("room-2",))
    with pytest.raises(AppointmentConflict):
        scheduler.create(clash)


def test_the_same_room_is_free_once_the_first_appointment_ends():
    scheduler = InMemoryScheduler([
        Availability("doctor-1", 0, time(9), time(18)),
        Availability("doctor-9", 0, time(9), time(18)),
    ])
    scheduler.create(Appointment("first", "doctor-1", "service-1", "client-1",
                                 datetime(2026, 7, 20, 10), timedelta(minutes=45),
                                 secondary_resource_ids=("room-2",)))

    later = Appointment("second", "doctor-9", "service-1", "client-2",
                        datetime(2026, 7, 20, 11), timedelta(minutes=45),
                        secondary_resource_ids=("room-2",))
    assert scheduler.create(later).secondary_resource_ids == ("room-2",)


def test_a_room_from_another_branch_is_refused():
    scheduler = InMemoryScheduler(
        [Availability("doctor-1", 0, time(9), time(18))],
        resources=[Resource("doctor-1", "Dra. Gómez", branch_id="branch-1"),
                   Resource("room-2", "Consultorio 2", branch_id="branch-9")],
    )

    crossed = Appointment("apt-1", "doctor-1", "service-1", "client-1",
                          datetime(2026, 7, 20, 10), timedelta(minutes=45),
                          branch_id="branch-1", secondary_resource_ids=("room-2",))
    with pytest.raises(ResourceBranchMismatch):
        scheduler.create(crossed)
