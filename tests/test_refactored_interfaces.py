import unittest
from unittest.mock import MagicMock

from business_intelligence.competitor_analyzer import CompetitorAnalyzer, CompetitorAnalysisResult
from intent.review_trend_detector import ReviewTrendDetector, ReviewTrendResult
from database.db import ScraperRepository


class TestCompetitorAnalyzerDecoupling(unittest.TestCase):

    def test_pure_domain_execution_without_db(self):
        """CompetitorAnalyzer can run without repo by providing raw_competitors directly."""
        analyzer = CompetitorAnalyzer(repo=None)
        
        raw_competitors = [
            {
                "business_name": "Rival Alpha",
                "website": "https://rivalalpha.com",
                "google_rating": 4.8,
                "opportunity_score": 30.0,
            },
            {
                "business_name": "Rival Beta",
                "website": "https://rivalbeta.com",
                "google_rating": 4.2,
                "opportunity_score": 60.0,
            }
        ]

        result = analyzer.analyze(
            business_id=1,
            business_name="Target Corp",
            category="gym",
            address="Kochi, Kerala",
            opportunity_score=80.0,
            raw_competitors=raw_competitors
        )

        self.assertIsInstance(result, CompetitorAnalysisResult)
        self.assertEqual(result.business_name, "Target Corp")
        self.assertEqual(len(result.competitors), 2)
        # Target score (80) - Rival Alpha score (30) = 50.0 gap
        self.assertEqual(result.competitors[0]["name"], "Rival Alpha")
        self.assertEqual(result.competitors[0]["score_gap"], 50.0)
        self.assertIn("Severe digital gap detected", result.competitor_gap_summary)

    def test_backward_compatibility_with_mock_repo(self):
        """CompetitorAnalyzer still queries repo if raw_competitors is None."""
        mock_repo = MagicMock()
        mock_repo.get_local_competitors.return_value = [
            {
                "business_name": "Local Gym",
                "website": "https://localgym.com",
                "google_rating": 4.5,
                "opportunity_score": 40.0,
            }
        ]

        analyzer = CompetitorAnalyzer(repo=mock_repo)
        result = analyzer.analyze(
            business_id=10,
            business_name="My Gym",
            category="gym",
            address="Trivandrum",
            opportunity_score=70.0
        )

        mock_repo.get_local_competitors.assert_called_once_with("Trivandrum", "gym", 10)
        self.assertEqual(len(result.competitors), 1)
        self.assertEqual(result.competitors[0]["name"], "Local Gym")


class TestReviewTrendDetectorDecoupling(unittest.TestCase):

    def test_pure_domain_execution_without_db(self):
        """ReviewTrendDetector can evaluate trend using pre-supplied previous_rating without repo."""
        detector = ReviewTrendDetector(repo=None)

        result = detector.analyze(
            business_name="Coffee House",
            current_rating=3.2,
            review_count=15,
            previous_rating=4.5,
            save_snapshot=False
        )

        self.assertIsInstance(result, ReviewTrendResult)
        self.assertEqual(result.business_name, "Coffee House")
        self.assertEqual(result.trend_direction, "declining")
        self.assertEqual(result.rating_delta, -1.3)
        self.assertEqual(result.rating_category, "average")
        self.assertEqual(result.review_volume_category, "low")
        self.assertGreater(result.review_trend_score, 50.0)

    def test_backward_compatibility_with_mock_repo(self):
        """ReviewTrendDetector queries snapshot and inserts new snapshot when repo is supplied."""
        mock_repo = MagicMock()
        mock_repo.get_latest_review_snapshot.return_value = {
            "rating": 4.0,
            "review_count": 80
        }

        detector = ReviewTrendDetector(repo=mock_repo)
        result = detector.analyze(
            business_name="Bakery",
            current_rating=4.2,
            review_count=100,
            business_id=42
        )

        mock_repo.get_latest_review_snapshot.assert_called_once_with(42)
        mock_repo.insert_review_snapshot.assert_called_once_with(42, 4.2, 100)
        self.assertEqual(result.previous_rating, 4.0)
        self.assertEqual(result.trend_direction, "improving")


class TestScraperRepositoryCrud(unittest.TestCase):

    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cur = MagicMock()
        self.mock_db.get_connection.return_value.__enter__.return_value = self.mock_conn
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cur
        self.repo = ScraperRepository(self.mock_db)

    def test_delete_all_businesses(self):
        result = self.repo.delete_all_businesses()
        self.assertTrue(result)
        self.mock_cur.execute.assert_called_once_with("DELETE FROM businesses;")

    def test_delete_business(self):
        self.mock_cur.fetchone.return_value = (1,)
        result = self.repo.delete_business(1)
        self.assertTrue(result)
        self.mock_cur.execute.assert_called_once_with(
            "DELETE FROM businesses WHERE id = %s RETURNING id;", (1,)
        )

    def test_batch_delete_businesses(self):
        self.mock_cur.rowcount = 3
        count = self.repo.batch_delete_businesses([1, 2, 3])
        self.assertEqual(count, 3)
        self.mock_cur.execute.assert_called_once_with(
            "DELETE FROM businesses WHERE id = ANY(%s);", ([1, 2, 3],)
        )

    def test_update_business(self):
        self.mock_cur.fetchone.return_value = (5,)
        updated = self.repo.update_business(
            5,
            {"business_name": "New Name", "outreach_status": "contacted"}
        )
        self.assertTrue(updated)
        sql_arg = self.mock_cur.execute.call_args[0][0]
        params_arg = self.mock_cur.execute.call_args[0][1]
        self.assertIn("UPDATE businesses SET", sql_arg)
        self.assertIn("business_name = %s", sql_arg)
        self.assertIn("outreach_status = %s", sql_arg)
        self.assertEqual(params_arg[-1], 5)


class TestApiServerEndpointDelegation(unittest.TestCase):

    def test_delete_all_businesses_delegation(self):
        from api_server import delete_all_businesses
        from unittest.mock import patch

        with patch("api_server.repo") as mock_repo:
            mock_repo.delete_all_businesses.return_value = True
            res = delete_all_businesses()
            self.assertTrue(res["success"])
            mock_repo.delete_all_businesses.assert_called_once()

    def test_delete_single_business_delegation(self):
        from api_server import delete_single_business
        from unittest.mock import patch

        with patch("api_server.repo") as mock_repo:
            mock_repo.delete_business.return_value = True
            res = delete_single_business("123")
            self.assertTrue(res["success"])
            self.assertEqual(res["id"], "123")
            mock_repo.delete_business.assert_called_once_with(123)

    def test_batch_delete_businesses_delegation(self):
        from api_server import batch_delete_businesses, BatchDeleteRequest
        from unittest.mock import patch

        with patch("api_server.repo") as mock_repo:
            mock_repo.batch_delete_businesses.return_value = 2
            res = batch_delete_businesses(BatchDeleteRequest(ids=["1", "2"]))
            self.assertTrue(res["success"])
            self.assertEqual(res["deleted_count"], 2)
            mock_repo.batch_delete_businesses.assert_called_once_with([1, 2])

    def test_update_business_field_delegation(self):
        from api_server import update_business_field, UpdateBusinessRequest
        from unittest.mock import patch

        with patch("api_server.repo") as mock_repo:
            mock_repo.update_business.return_value = True
            res = update_business_field(45, UpdateBusinessRequest(outreach_status="contacted"))
            self.assertTrue(res["success"])
            self.assertEqual(res["updated"]["outreach_status"], "contacted")
            mock_repo.update_business.assert_called_once_with(45, {"outreach_status": "contacted"})


if __name__ == "__main__":
    unittest.main()
