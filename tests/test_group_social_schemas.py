import unittest
from uuid import uuid4

from api.routes import ONLINE_STATUSES, STUDY_STATUSES, _group_notification_recipient_filter
from schemas.user import (
    GroupCreateRequest,
    GroupMembersResponse,
    GroupResponse,
    GroupJoinRequest,
    GroupMemberResponse,
    GroupMemberStatusUpdateRequest,
    GroupPetPlacementRequest,
    GroupNotificationMarkReadResponse,
    GroupNotificationResponse,
    GroupNotificationUnreadCountResponse,
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
            group_today_study_seconds=1800,
            created_at="2026-06-05T12:00:00Z",
        )

        self.assertEqual(payload.visibility, "private")
        self.assertEqual(payload.group_today_study_seconds, 1800)

    def test_group_members_response_exposes_today_study_seconds(self):
        member = GroupMemberResponse(
            user_id=uuid4(),
            nickname="로기",
            major="engineering",
            petType="cat",
            petLevel=2,
            role="member",
            online_status="online",
            study_status="idle",
            active_study_session_id=None,
            positionX=80,
            positionY=340,
            last_seen_at="2026-06-05T12:00:00Z",
            total_study_seconds=7200,
            today_study_seconds=1800,
        )
        payload = GroupMembersResponse(
            group_id=1,
            group_name="오픈소스 8조",
            group_total_study_seconds=7200,
            group_today_study_seconds=1800,
            members=[member],
        )

        self.assertEqual(payload.group_today_study_seconds, 1800)
        self.assertEqual(payload.members[0].today_study_seconds, 1800)
        self.assertEqual(payload.members[0].positionX, 80)
        self.assertEqual(payload.members[0].positionY, 340)
        self.assertEqual(payload.members[0].major, "engineering")
        self.assertEqual(payload.members[0].petType, "cat")
        self.assertEqual(payload.members[0].petLevel, 2)

    def test_group_join_request_accepts_invite_code(self):
        payload = GroupJoinRequest(invite_code="ABCD1234")

        self.assertEqual(payload.invite_code, "ABCD1234")

    def test_group_member_status_update_defaults_to_idle_online(self):
        payload = GroupMemberStatusUpdateRequest()

        self.assertEqual(payload.online_status, "online")
        self.assertEqual(payload.study_status, "idle")
        self.assertIsNone(payload.active_study_session_id)

    def test_group_pet_placement_accepts_frontend_pixel_coordinates(self):
        payload = GroupPetPlacementRequest.model_validate(
            {
                "positionX": 210,
                "positionY": 360,
            }
        )

        self.assertEqual(payload.position_x, 210)
        self.assertEqual(payload.position_y, 360)

    def test_group_poke_request_accepts_target_user(self):
        target_user_id = uuid4()
        payload = GroupPokeCreateRequest(
            target_user_id=target_user_id,
            reaction_type="heart",
            message="공부하자",
        )

        self.assertEqual(payload.target_user_id, target_user_id)
        self.assertEqual(payload.reaction_type, "heart")
        self.assertEqual(payload.message, "공부하자")

    def test_group_notification_response_exposes_reaction_context(self):
        sender_user_id = uuid4()
        target_user_id = uuid4()
        payload = GroupNotificationResponse(
            id=1,
            group_id=2,
            group_name="오픈소스 8조",
            event_type="reaction",
            sender_user_id=sender_user_id,
            sender_nickname="로기",
            target_user_id=target_user_id,
            target_nickname="코덱스",
            reaction_type="fighting",
            message="힘내",
            is_read=False,
            created_at="2026-06-05T12:00:00Z",
        )

        self.assertEqual(payload.sender_user_id, sender_user_id)
        self.assertEqual(payload.reaction_type, "fighting")
        self.assertFalse(payload.is_read)

    def test_group_join_notification_response_allows_join_event(self):
        actor_user_id = uuid4()
        payload = GroupNotificationResponse(
            id=2,
            group_id=2,
            group_name="오픈소스 8조",
            event_type="join",
            sender_user_id=actor_user_id,
            sender_nickname="새멤버",
            target_user_id=actor_user_id,
            target_nickname="새멤버",
            reaction_type=None,
            message="그룹 참여",
            is_read=False,
            created_at="2026-06-05T12:00:00Z",
        )

        self.assertEqual(payload.event_type, "join")
        self.assertIsNone(payload.reaction_type)

    def test_group_notification_badge_responses_expose_camel_count(self):
        unread = GroupNotificationUnreadCountResponse(unread_count=3, unreadCount=3)
        marked = GroupNotificationMarkReadResponse(
            message="그룹 알림 읽음 처리",
            marked_count=3,
            unread_count=0,
            unreadCount=0,
        )

        self.assertEqual(unread.unreadCount, 3)
        self.assertEqual(marked.unreadCount, 0)

    def test_group_notification_filter_limits_reactions_to_target(self):
        user_id = uuid4()
        compiled = str(_group_notification_recipient_filter(user_id))

        self.assertIn("event_type", compiled)
        self.assertIn("target_user_id", compiled)
        self.assertIn("actor_user_id", compiled)


if __name__ == "__main__":
    unittest.main()
