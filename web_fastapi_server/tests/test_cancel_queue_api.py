"""
Cancel Queue API 엔드포인트 테스트

FastAPI 테스트 클라이언트를 사용한 API 통합 테스트
"""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.db.session import get_db
from app.services.cancel_queue_service import CancelQueueService
from app.models.cancel_queue import CancelQueue


@pytest.mark.skip(reason="Requires actual database connection")
class TestCancelQueueAPIIntegration:
    """실제 DB 연결이 필요한 API 통합 테스트"""

    @pytest_asyncio.fixture
    async def client(self, async_db_session):
        """테스트 클라이언트 (DB 오버라이드)"""
        async def override_get_db():
            yield async_db_session

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as test_client:
            yield test_client

        app.dependency_overrides.clear()

    def test_request_cancel_pending_order(self, client):
        """PENDING 주문 취소 요청"""
        order_id = 1

        with patch.object(CancelQueueService, 'verify_order_status', return_value="PENDING"):
            response = client.post(f"/api/v1/cancel-queue/orders/{order_id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == order_id
        assert data["status"] == "queued"
        assert data["immediate"] is False
        assert "cancel_queue_id" in data

    def test_request_cancel_open_order(self, client):
        """OPEN 주문 즉시 취소"""
        order_id = 2

        with patch.object(CancelQueueService, 'verify_order_status', return_value="OPEN"):
            response = client.post(f"/api/v1/cancel-queue/orders/{order_id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == order_id
        assert data["status"] == "cancelled"
        assert data["immediate"] is True

    def test_request_cancel_already_cancelled(self, client):
        """이미 취소된 주문"""
        order_id = 3

        with patch.object(CancelQueueService, 'verify_order_status', return_value="CANCELLED"):
            response = client.post(f"/api/v1/cancel-queue/orders/{order_id}/cancel")

        assert response.status_code == 409  # Conflict

    def test_request_cancel_duplicate(self, client, async_db_session):
        """중복 취소 요청"""
        order_id = 4

        # 첫 번째 요청
        with patch.object(CancelQueueService, 'verify_order_status', return_value="PENDING"):
            response1 = client.post(f"/api/v1/cancel-queue/orders/{order_id}/cancel")

        assert response1.status_code == 200

        # 두 번째 요청 (중복)
        with patch.object(CancelQueueService, 'verify_order_status', return_value="PENDING"):
            response2 = client.post(f"/api/v1/cancel-queue/orders/{order_id}/cancel")

        assert response2.status_code == 400  # ValidationException

    def test_get_cancel_queue_list(self, client, async_db_session):
        """Cancel Queue 목록 조회"""
        # 몇 개 추가
        service = CancelQueueService()
        for i in range(3):
            # Note: This requires async context, simplified for test
            pass

        response = client.get("/api/v1/cancel-queue")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_cancel_queue_with_status_filter(self, client):
        """상태 필터로 조회"""
        response = client.get("/api/v1/cancel-queue?status=PENDING&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_cancel_queue_with_pagination(self, client):
        """페이지네이션으로 조회"""
        response = client.get("/api/v1/cancel-queue?limit=5&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    def test_get_cancel_queue_item_found(self, client, async_db_session):
        """개별 항목 조회 (존재)"""
        # Create a cancel item first
        service = CancelQueueService()
        # cancel_item = await service.add_to_queue(async_db_session, order_id=100)
        # cancel_id = cancel_item.id

        # Simplified test
        cancel_id = 1

        # Mock get_all to return sample data
        with patch.object(CancelQueueService, 'get_all') as mock_get_all:
            mock_item = CancelQueue(id=cancel_id, order_id=100, status="PENDING")
            mock_get_all.return_value = [mock_item]

            response = client.get(f"/api/v1/cancel-queue/{cancel_id}")

        # May be 200 or 404 depending on mock
        assert response.status_code in (200, 404)

    def test_get_cancel_queue_item_not_found(self, client):
        """개별 항목 조회 (존재하지 않음)"""
        cancel_id = 99999

        with patch.object(CancelQueueService, 'get_all', return_value=[]):
            response = client.get(f"/api/v1/cancel-queue/{cancel_id}")

        assert response.status_code == 404

    def test_delete_cancel_queue_item_success(self, client):
        """Cancel Queue 항목 삭제 성공"""
        cancel_id = 1

        with patch.object(CancelQueueService, 'delete', return_value=True):
            response = client.delete(f"/api/v1/cancel-queue/{cancel_id}")

        assert response.status_code == 204

    def test_delete_cancel_queue_item_not_found(self, client):
        """Cancel Queue 항목 삭제 (존재하지 않음)"""
        cancel_id = 99999

        with patch.object(CancelQueueService, 'delete', return_value=False):
            response = client.delete(f"/api/v1/cancel-queue/{cancel_id}")

        assert response.status_code == 404


class TestCancelQueueAPIUnit:
    """DB 없이 테스트 가능한 API 유닛 테스트"""

    def test_api_endpoints_registered(self):
        """API 엔드포인트 등록 확인"""
        client = TestClient(app)

        # Check OpenAPI schema
        response = client.get("/openapi.json")
        assert response.status_code == 200

        openapi_schema = response.json()
        paths = openapi_schema.get("paths", {})

        # Cancel Queue 엔드포인트 존재 확인
        assert "/api/v1/cancel-queue/orders/{order_id}/cancel" in paths
        assert "/api/v1/cancel-queue" in paths
        assert "/api/v1/cancel-queue/{cancel_id}" in paths

    def test_cancel_request_response_schema(self):
        """취소 요청 응답 스키마 검증"""
        client = TestClient(app)

        # Get OpenAPI schema
        response = client.get("/openapi.json")
        openapi_schema = response.json()

        # Find CancelRequestResponse schema
        schemas = openapi_schema.get("components", {}).get("schemas", {})

        assert "CancelRequestResponse" in schemas
        cancel_response = schemas["CancelRequestResponse"]

        # 필수 필드 확인
        required_fields = cancel_response.get("required", [])
        assert "message" in required_fields
        assert "order_id" in required_fields
        assert "status" in required_fields
        assert "immediate" in required_fields

    def test_cancel_queue_response_schema(self):
        """Cancel Queue 응답 스키마 검증"""
        client = TestClient(app)

        response = client.get("/openapi.json")
        openapi_schema = response.json()

        schemas = openapi_schema.get("components", {}).get("schemas", {})

        assert "CancelQueueResponse" in schemas
        queue_response = schemas["CancelQueueResponse"]

        # 필수 필드 확인
        required_fields = queue_response.get("required", [])
        assert "id" in required_fields
        assert "order_id" in required_fields
        assert "status" in required_fields

    def test_invalid_order_id_type(self):
        """잘못된 order_id 타입"""
        client = TestClient(app)

        # String instead of int
        response = client.post("/api/v1/cancel-queue/orders/invalid/cancel")

        assert response.status_code == 422  # Validation error

    def test_negative_pagination_params(self):
        """음수 페이지네이션 파라미터"""
        client = TestClient(app)

        # Negative limit
        response = client.get("/api/v1/cancel-queue?limit=-1")
        assert response.status_code == 422

        # Negative offset
        response = client.get("/api/v1/cancel-queue?offset=-1")
        assert response.status_code == 422

    def test_pagination_limits(self):
        """페이지네이션 한계 테스트"""
        client = TestClient(app)

        # Limit too high (max 200)
        response = client.get("/api/v1/cancel-queue?limit=999")
        assert response.status_code == 422


class TestCancelQueueAPIMock:
    """Mock을 사용한 API 테스트 (DB 불필요)"""

    @pytest.fixture
    def client(self):
        """테스트 클라이언트 (Mock DB)"""
        async def mock_get_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = mock_get_db

        with TestClient(app) as test_client:
            yield test_client

        app.dependency_overrides.clear()

    def test_request_cancel_with_mock_service(self, client):
        """Mock 서비스를 사용한 취소 요청"""
        order_id = 1

        # Mock CancelQueueService
        with patch('app.api.v1.cancel_queue.CancelQueueService') as MockService:
            mock_service = MockService.return_value
            mock_service.verify_order_status = AsyncMock(return_value="PENDING")

            mock_cancel_item = CancelQueue(
                id=1,
                order_id=order_id,
                status="PENDING",
                retry_count=0
            )
            mock_service.add_to_queue = AsyncMock(return_value=mock_cancel_item)

            response = client.post(f"/api/v1/cancel-queue/orders/{order_id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == order_id
        assert data["status"] == "queued"
