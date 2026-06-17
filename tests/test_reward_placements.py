import unittest

from pydantic import ValidationError

from schemas import FurniturePlacementRequest, PetPlacementRequest


class RewardPlacementSchemaTest(unittest.TestCase):
    def test_furniture_placement_accepts_frontend_pixel_coordinates(self):
        payload = FurniturePlacementRequest.model_validate(
            {
                "furniture_item_id": 1,
                "placed": True,
                "position_x": 60,
                "position_y": 340,
            }
        )

        self.assertEqual(payload.furniture_item_id, 1)
        self.assertEqual(payload.position_x, 60)
        self.assertEqual(payload.position_y, 340)

    def test_furniture_placement_accepts_camel_case_payload(self):
        payload = FurniturePlacementRequest.model_validate(
            {
                "furnitureItemId": 1,
                "placed": True,
                "positionX": -12,
                "positionY": 340,
            }
        )

        self.assertEqual(payload.furniture_item_id, 1)
        self.assertEqual(payload.position_x, -12)
        self.assertEqual(payload.position_y, 340)

    def test_pet_placement_accepts_frontend_pixel_coordinates(self):
        payload = PetPlacementRequest.model_validate(
            {
                "placed": True,
                "position_x": 120,
                "position_y": 280,
            }
        )

        self.assertTrue(payload.placed)
        self.assertEqual(payload.position_x, 120)
        self.assertEqual(payload.position_y, 280)

    def test_placement_rejects_extreme_coordinates(self):
        with self.assertRaises(ValidationError):
            PetPlacementRequest.model_validate(
                {
                    "placed": True,
                    "position_x": 10001,
                    "position_y": 0,
                }
            )


if __name__ == "__main__":
    unittest.main()
