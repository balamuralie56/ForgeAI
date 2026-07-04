"""
Unit and concurrency tests for the ForgeAI Event Bus.
"""

import asyncio
import threading
import time
import unittest
from datetime import datetime
from typing import List

from forge_core.event_bus import Event, ForgeAIEventBus, SubscriptionError


class TestEventBus(unittest.TestCase):
    """Test suite for validating synchronous/asynchronous Event Bus capabilities."""

    def test_sync_subscription_and_publish(self) -> None:
        """Tests subscribing a standard callback and publishing to it synchronously."""
        bus = ForgeAIEventBus()
        bus.initialize()

        received_events: List[Event] = []

        def callback(event: Event) -> None:
            received_events.append(event)

        sub_id = bus.subscribe("test.event", callback)
        self.assertIsNotNone(sub_id)

        meta = {"origin": "test"}
        payload = {"data": "value"}
        event = Event(event_type="test.event", metadata=meta, data=payload)

        bus.publish(event)

        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].event_type, "test.event")
        self.assertEqual(received_events[0].metadata["origin"], "test")
        self.assertEqual(received_events[0].data["data"], "value")
        self.assertIsInstance(received_events[0].timestamp, datetime)

        # Test unsubscribe
        bus.unsubscribe(sub_id)
        bus.publish(event)
        self.assertEqual(len(received_events), 1)  # unchanged

        bus.shutdown()

    def test_multiple_subscribers_wildcard(self) -> None:
        """Tests that multiple subscribers receive the same event, including wildcard subscribers."""
        bus = ForgeAIEventBus()
        bus.initialize()

        count_a = 0
        count_wildcard = 0

        def cb_a(event: Event) -> None:
            nonlocal count_a
            count_a += 1

        def cb_wildcard(event: Event) -> None:
            nonlocal count_wildcard
            count_wildcard += 1

        bus.subscribe("topic.a", cb_a)
        bus.subscribe("*", cb_wildcard)

        # Publish to topic.a (should trigger both)
        bus.publish(Event("topic.a"))
        self.assertEqual(count_a, 1)
        self.assertEqual(count_wildcard, 1)

        # Publish to topic.b (should trigger only wildcard)
        bus.publish(Event("topic.b"))
        self.assertEqual(count_a, 1)
        self.assertEqual(count_wildcard, 2)

        bus.shutdown()

    def test_unsubscribe_nonexistent_raises(self) -> None:
        """Tests that unsubscribing with an invalid ID raises SubscriptionError."""
        bus = ForgeAIEventBus()
        bus.initialize()

        with self.assertRaises(SubscriptionError):
            bus.unsubscribe("non-existent-uuid")

        bus.shutdown()

    def test_publish_async_subscribers(self) -> None:
        """Tests async publish with async and sync subscribers."""
        bus = ForgeAIEventBus()
        bus.initialize()

        sync_received = False
        async_received = False

        def sync_cb(event: Event) -> None:
            nonlocal sync_received
            sync_received = True

        async def async_cb(event: Event) -> None:
            nonlocal async_received
            async_received = True

        bus.subscribe("async.topic", sync_cb)
        bus.subscribe("async.topic", async_cb)

        async def run_async_test() -> None:
            event = Event("async.topic")
            await bus.publish_async(event)

        asyncio.run(run_async_test())

        self.assertTrue(sync_received)
        self.assertTrue(async_received)

        bus.shutdown()

    def test_thread_safety_concurrency(self) -> None:
        """Tests concurrent subscriptions and publishing across multiple threads."""
        bus = ForgeAIEventBus()
        bus.initialize()

        run_flag = True
        errors: List[Exception] = []

        def subscriber_thread() -> None:
            while run_flag:
                try:
                    sub_id = bus.subscribe("concurrency.test", lambda e: None)
                    time.sleep(0.001)
                    bus.unsubscribe(sub_id)
                except Exception as e:
                    errors.append(e)

        def publisher_thread() -> None:
            event = Event("concurrency.test")
            while run_flag:
                try:
                    bus.publish(event)
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(e)

        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=subscriber_thread))
            threads.append(threading.Thread(target=publisher_thread))

        for t in threads:
            t.start()

        time.sleep(0.2)
        run_flag = False

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Encountered concurrency errors: {errors}")
        bus.shutdown()


if __name__ == "__main__":
    unittest.main()
