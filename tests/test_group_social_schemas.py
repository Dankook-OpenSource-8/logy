import unittest
from uuid import uuid4

from api.routes import ONLINE_STATUSES, STUDY_STATUSES
from schemas.user import (
    GroupCreateRequest,
    GroupResponse,
    GroupJoinRequest,
    GroupMemberStatusUpdateRequest,
    GroupPokeCreateRequest,
)


class GroupSocialSchemaTest(unittest.TestCase):
    def test_supported_presence_status_values_are_available(self):
        self.assertEqual(ONLINE_STATUSES, {"online", "offline"})
        self.assertIn("studying", STUDY_STATUSES)
        self.assertIn("verifying", STUDY_STATUSES)

    def test_group_create_request_accepts_name(self):
        payload = GroupCreateRequest(name="오픈소스 8조")

        self.assertEqual(payload.name, "오픈소스 8조")
        self.assertEqual(payload.visibility, "private")

    def test_group_create_request_accepts_public_visibility(self):
        payload = GroupCreateRequest(name="오픈소스 8조", visibility="public")

        self.assertEqual(payload.visibility, "public")

    def test_group_response_exposes_visibility_for_group_badges(self):
        payload = GroupResponse(
            id=1,
            name="오픈소스 8조",
            visibility="private",
            invite_code="ABCD1234",
            owner_user_id=uuid4(),
            member_count=3,
            group_total_study_seconds=7200,
            created_at="2026-06-05T12:00:00Z",
        )

        self.assertEqual(payload.visibility, "private")

    def test_group_join_request_accepts_invite_code(self):
        payload = GroupJoinRequest(invite_code="ABCD1234")

        self.assertEqual(payload.invite_code, "ABCD1234")

    def test_group_member_status_update_defaults_to_idle_online(self):
        payload = GroupMemberStatusUpdateRequest()

        self.assertEqual(payload.online_status, "online")
        self.assertEqual(payload.study_status, "idle")
        self.assertIsNone(payload.active_study_session_id)

    def test_group_poke_request_accepts_target_user(self):
        target_user_id = uuid4()
        payload = GroupPokeCreateRequest(
            target_user_id=target_user_id,
            message="공부하자",
        )

        self.assertEqual(payload.target_user_id, target_user_id)
        self.assertEqual(payload.message, "공부하자")


if __name__ == "__main__":
    unittest.main()
