import unittest

from core.expo_push import build_expo_push_messages


class ExpoPushTest(unittest.TestCase):
    def test_build_messages_keeps_expo_tokens_only(self):
        messages = build_expo_push_messages(
            [
                "ExponentPushToken[abc]",
                "ExpoPushToken[def]",
                "not-a-token",
                "",
            ],
            "그룹 알림",
            "로기님이 그룹에 참여했어요",
            {"groupId": 1},
        )

        self.assertEqual([message["to"] for message in messages], [
            "ExponentPushToken[abc]",
            "ExpoPushToken[def]",
        ])
        self.assertEqual(messages[0]["title"], "그룹 알림")
        self.assertEqual(messages[0]["data"], {"groupId": 1})


if __name__ == "__main__":
    unittest.main()
