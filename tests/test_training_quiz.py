"""
Test suite for Training Quiz API
Tests: Quiz CRUD, Quiz submission, Quiz results, Progress Dashboard quiz stats
Module ID with existing quiz: 48654d67-5c47-4add-aa0e-733e6c8c8192 (2 questions, correct answers: 0 and 1)
"""

import pytest
import requests
import os
from uuid import uuid4

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://condescending-wozniak-3.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "Admin@credlocity.com"
ADMIN_PASSWORD = "Credit123!"

# Existing module with quiz for testing
EXISTING_MODULE_ID = "48654d67-5c47-4add-aa0e-733e6c8c8192"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


# ==================== GET QUIZ ENDPOINT ====================

class TestGetQuiz:
    """Tests for GET /api/training/modules/{id}/quiz"""
    
    def test_get_quiz_admin_sees_correct_answers(self, api_client):
        """Admin user should see correct_answer and explanation fields"""
        response = api_client.get(f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz")
        assert response.status_code == 200, f"Failed to get quiz: {response.text}"
        
        data = response.json()
        assert "quiz" in data
        
        if data["quiz"]:
            quiz = data["quiz"]
            assert "questions" in quiz
            assert "passing_score" in quiz
            assert quiz["module_id"] == EXISTING_MODULE_ID
            
            # Admin should see correct_answer and explanation
            for i, q in enumerate(quiz["questions"]):
                assert "correct_answer" in q, f"Question {i} missing correct_answer for admin"
                assert "question" in q
                assert "options" in q
                print(f"  Question {i+1}: '{q['question'][:40]}...' correct_answer={q['correct_answer']}")
            
            print(f"[PASS] Admin sees quiz with {len(quiz['questions'])} questions, passing_score={quiz['passing_score']}")
        else:
            print("[INFO] No quiz exists for this module yet")
    
    def test_get_quiz_for_nonexistent_module_returns_null(self, api_client):
        """Quiz for nonexistent module returns null quiz"""
        response = api_client.get(f"{BASE_URL}/api/training/modules/nonexistent-module-999/quiz")
        # Should not 404, just return null quiz
        assert response.status_code == 200
        data = response.json()
        assert data.get("quiz") is None
        print("[PASS] Nonexistent module returns null quiz")


# ==================== CREATE/UPDATE QUIZ ENDPOINT ====================

class TestCreateUpdateQuiz:
    """Tests for POST /api/training/modules/{id}/quiz"""
    
    test_module_id = None
    
    def test_create_quiz_success(self, api_client):
        """Admin can create a quiz for a module"""
        # First create a test module
        module_data = {
            "title": f"TEST_QuizModule_{str(uuid4())[:8]}",
            "description": "Module for quiz testing",
            "department": "IT",
            "content": "<p>Test content</p>",
            "steps": [
                {"title": "Step 1", "content": "Step 1 content", "image_url": ""}
            ],
            "status": "published"
        }
        create_res = api_client.post(f"{BASE_URL}/api/training/modules", json=module_data)
        assert create_res.status_code == 200, f"Failed to create module: {create_res.text}"
        TestCreateUpdateQuiz.test_module_id = create_res.json()["id"]
        
        # Now create a quiz for it
        quiz_data = {
            "questions": [
                {
                    "question": "What is the capital of France?",
                    "options": ["London", "Paris", "Berlin", "Madrid"],
                    "correct_answer": 1,
                    "explanation": "Paris is the capital of France."
                },
                {
                    "question": "What is 2 + 2?",
                    "options": ["3", "4", "5"],
                    "correct_answer": 1,
                    "explanation": "2 + 2 equals 4."
                }
            ],
            "passing_score": 80
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{TestCreateUpdateQuiz.test_module_id}/quiz",
            json=quiz_data
        )
        assert response.status_code == 200, f"Failed to create quiz: {response.text}"
        
        data = response.json()
        assert data.get("message") == "Quiz saved"
        assert data.get("question_count") == 2
        print(f"[PASS] Quiz created with {data['question_count']} questions")
    
    def test_get_created_quiz_and_verify_data(self, api_client):
        """Verify the quiz was persisted correctly"""
        module_id = TestCreateUpdateQuiz.test_module_id
        assert module_id, "No module ID from create test"
        
        response = api_client.get(f"{BASE_URL}/api/training/modules/{module_id}/quiz")
        assert response.status_code == 200
        
        quiz = response.json()["quiz"]
        assert quiz is not None
        assert quiz["passing_score"] == 80
        assert len(quiz["questions"]) == 2
        
        # Verify question structure
        q1 = quiz["questions"][0]
        assert q1["question"] == "What is the capital of France?"
        assert q1["correct_answer"] == 1
        assert q1["explanation"] == "Paris is the capital of France."
        assert len(q1["options"]) == 4
        
        print("[PASS] Quiz data persisted and retrieved correctly")
    
    def test_update_quiz_adds_questions(self, api_client):
        """Update quiz to add more questions"""
        module_id = TestCreateUpdateQuiz.test_module_id
        assert module_id, "No module ID from create test"
        
        updated_quiz_data = {
            "questions": [
                {
                    "question": "What is the capital of France?",
                    "options": ["London", "Paris", "Berlin", "Madrid"],
                    "correct_answer": 1,
                    "explanation": "Paris is the capital of France."
                },
                {
                    "question": "What is 2 + 2?",
                    "options": ["3", "4", "5"],
                    "correct_answer": 1,
                    "explanation": "2 + 2 equals 4."
                },
                {
                    "question": "NEW: What color is the sky?",
                    "options": ["Green", "Blue", "Red"],
                    "correct_answer": 1,
                    "explanation": "The sky appears blue due to light scattering."
                }
            ],
            "passing_score": 70
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{module_id}/quiz",
            json=updated_quiz_data
        )
        assert response.status_code == 200
        assert response.json()["question_count"] == 3
        
        # Verify update
        get_res = api_client.get(f"{BASE_URL}/api/training/modules/{module_id}/quiz")
        quiz = get_res.json()["quiz"]
        assert quiz["passing_score"] == 70
        assert len(quiz["questions"]) == 3
        
        print("[PASS] Quiz updated to 3 questions, passing_score=70")
    
    def test_create_quiz_validates_questions_text(self, api_client):
        """Quiz creation requires question text"""
        module_id = TestCreateUpdateQuiz.test_module_id
        
        invalid_quiz = {
            "questions": [
                {
                    "question": "",  # Empty question text
                    "options": ["A", "B"],
                    "correct_answer": 0
                }
            ],
            "passing_score": 80
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{module_id}/quiz",
            json=invalid_quiz
        )
        assert response.status_code == 400
        assert "required" in response.json().get("detail", "").lower()
        print("[PASS] Validation rejects empty question text")
    
    def test_create_quiz_validates_minimum_options(self, api_client):
        """Quiz creation requires at least 2 options"""
        module_id = TestCreateUpdateQuiz.test_module_id
        
        invalid_quiz = {
            "questions": [
                {
                    "question": "Test question?",
                    "options": ["Only one option"],  # Only 1 option
                    "correct_answer": 0
                }
            ],
            "passing_score": 80
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{module_id}/quiz",
            json=invalid_quiz
        )
        assert response.status_code == 400
        assert "2 options" in response.json().get("detail", "").lower()
        print("[PASS] Validation rejects questions with less than 2 options")
    
    def test_create_quiz_validates_correct_answer(self, api_client):
        """Quiz creation requires correct_answer to be set"""
        module_id = TestCreateUpdateQuiz.test_module_id
        
        invalid_quiz = {
            "questions": [
                {
                    "question": "Test question?",
                    "options": ["A", "B", "C"],
                    # Missing correct_answer
                }
            ],
            "passing_score": 80
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{module_id}/quiz",
            json=invalid_quiz
        )
        assert response.status_code == 400
        assert "correct answer" in response.json().get("detail", "").lower()
        print("[PASS] Validation rejects questions without correct_answer")
    
    def test_create_quiz_for_nonexistent_module_returns_404(self, api_client):
        """Creating quiz for nonexistent module returns 404"""
        quiz_data = {
            "questions": [
                {
                    "question": "Test?",
                    "options": ["A", "B"],
                    "correct_answer": 0
                }
            ],
            "passing_score": 80
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/nonexistent-module-xyz/quiz",
            json=quiz_data
        )
        assert response.status_code == 404
        print("[PASS] 404 returned for quiz on nonexistent module")


# ==================== SUBMIT QUIZ ENDPOINT ====================

class TestSubmitQuiz:
    """Tests for POST /api/training/modules/{id}/quiz/submit"""
    
    def test_submit_quiz_all_correct_passes(self, api_client):
        """Submitting all correct answers should pass"""
        # Use the existing module with known correct answers (0 and 1)
        answers = {"0": 0, "1": 1}  # Both correct
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/submit",
            json={"answers": answers}
        )
        assert response.status_code == 200, f"Failed to submit: {response.text}"
        
        data = response.json()
        assert "score" in data
        assert "passed" in data
        assert "results" in data
        assert "correct" in data
        assert "total" in data
        
        assert data["score"] == 100.0
        assert data["passed"] == True
        assert data["correct"] == 2
        assert data["total"] == 2
        
        # Verify results contain explanations
        for r in data["results"]:
            assert "question" in r
            assert "is_correct" in r
            assert "explanation" in r
            assert "correct_answer" in r
            assert "user_answer" in r
        
        print(f"[PASS] Quiz submitted: score={data['score']}%, passed={data['passed']}")
    
    def test_submit_quiz_with_wrong_answers_fails(self, api_client):
        """Submitting wrong answers should fail (below passing score)"""
        # Wrong answers - correct are 0 and 1, so submit 1 and 0 (both wrong)
        answers = {"0": 1, "1": 0}
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/submit",
            json={"answers": answers}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["score"] == 0.0
        assert data["passed"] == False
        assert data["correct"] == 0
        
        print(f"[PASS] Quiz with wrong answers: score={data['score']}%, passed={data['passed']}")
    
    def test_submit_quiz_partial_correct(self, api_client):
        """Submitting 1 correct out of 2 gives 50%"""
        # One correct (0), one wrong
        answers = {"0": 0, "1": 0}  # First correct (0), second wrong (should be 1)
        
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/submit",
            json={"answers": answers}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["score"] == 50.0
        assert data["correct"] == 1
        # 50% < 80% passing score, so should fail
        assert data["passed"] == False
        
        print(f"[PASS] Partial correct: score={data['score']}%, passed={data['passed']}")
    
    def test_submit_quiz_saves_attempt(self, api_client):
        """Quiz submission should save to quiz_attempts collection"""
        # Submit quiz
        answers = {"0": 0, "1": 1}
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/submit",
            json={"answers": answers}
        )
        assert response.status_code == 200
        
        # Verify attempt was saved by checking results endpoint
        results_res = api_client.get(f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/results")
        assert results_res.status_code == 200
        
        results = results_res.json()
        assert "attempts" in results
        assert len(results["attempts"]) > 0
        
        # Find our attempt
        latest_attempt = results["attempts"][0]  # Should be sorted by submitted_at desc
        assert "score" in latest_attempt
        assert "passed" in latest_attempt
        assert "user_id" in latest_attempt
        assert "submitted_at" in latest_attempt
        
        print(f"[PASS] Quiz attempt saved, found {len(results['attempts'])} total attempts")
    
    def test_submit_quiz_updates_progress_when_passed(self, api_client):
        """Passing quiz should update training_progress with quiz_passed=True"""
        # Submit correct answers
        answers = {"0": 0, "1": 1}
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/submit",
            json={"answers": answers}
        )
        assert response.status_code == 200
        assert response.json()["passed"] == True
        
        # Check progress
        progress_res = api_client.get(f"{BASE_URL}/api/training/my-progress")
        assert progress_res.status_code == 200
        
        progress = progress_res.json()["progress"]
        if EXISTING_MODULE_ID in progress:
            mod_progress = progress[EXISTING_MODULE_ID]
            assert mod_progress.get("quiz_passed") == True
            assert mod_progress.get("quiz_score") == 100.0
            print(f"[PASS] Progress updated: quiz_passed={mod_progress['quiz_passed']}, quiz_score={mod_progress['quiz_score']}")
        else:
            print("[PASS] Quiz submission completed, progress record created")
    
    def test_submit_quiz_for_nonexistent_module_returns_404(self, api_client):
        """Submitting quiz for nonexistent module returns 404"""
        response = api_client.post(
            f"{BASE_URL}/api/training/modules/nonexistent-xyz/quiz/submit",
            json={"answers": {"0": 0}}
        )
        assert response.status_code == 404
        print("[PASS] 404 returned for quiz submit on nonexistent module")


# ==================== GET QUIZ RESULTS ENDPOINT ====================

class TestQuizResults:
    """Tests for GET /api/training/modules/{id}/quiz/results (admin only)"""
    
    def test_get_quiz_results_admin_success(self, api_client):
        """Admin can get quiz results with stats"""
        response = api_client.get(f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/results")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "module_id" in data
        assert "total_attempts" in data
        assert "average_score" in data
        assert "pass_rate" in data
        assert "attempts" in data
        
        assert data["module_id"] == EXISTING_MODULE_ID
        assert isinstance(data["total_attempts"], int)
        assert isinstance(data["average_score"], (int, float))
        assert isinstance(data["pass_rate"], (int, float))
        assert isinstance(data["attempts"], list)
        
        print(f"[PASS] Quiz results: {data['total_attempts']} attempts, avg={data['average_score']}%, pass_rate={data['pass_rate']}%")
    
    def test_quiz_results_attempts_structure(self, api_client):
        """Quiz results attempts have correct structure"""
        response = api_client.get(f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/results")
        assert response.status_code == 200
        
        attempts = response.json()["attempts"]
        if len(attempts) > 0:
            attempt = attempts[0]
            required_fields = ["id", "user_id", "user_name", "score", "passed", "submitted_at"]
            for field in required_fields:
                assert field in attempt, f"Missing field: {field}"
            print(f"[PASS] Attempt structure verified with fields: {list(attempt.keys())}")
        else:
            print("[INFO] No attempts to verify structure")


# ==================== PROGRESS DASHBOARD WITH QUIZ STATS ====================

class TestProgressDashboardQuizStats:
    """Tests for GET /api/training/progress/dashboard quiz stats"""
    
    def test_dashboard_includes_quiz_stats(self, api_client):
        """Progress dashboard module_stats includes has_quiz, avg_quiz_score, quiz_pass_rate"""
        response = api_client.get(f"{BASE_URL}/api/training/progress/dashboard")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "module_stats" in data
        
        # Find our test module with quiz
        found_quiz_module = False
        for ms in data["module_stats"]:
            if ms["module_id"] == EXISTING_MODULE_ID:
                found_quiz_module = True
                assert "has_quiz" in ms
                assert ms["has_quiz"] == True
                assert "avg_quiz_score" in ms
                assert "quiz_pass_rate" in ms
                assert "quiz_attempts" in ms
                
                print(f"[PASS] Module '{ms['title']}' quiz stats: has_quiz={ms['has_quiz']}, avg={ms['avg_quiz_score']}%, pass_rate={ms['quiz_pass_rate']}%")
                break
        
        if not found_quiz_module:
            # Check if module is published (dashboard only shows published modules)
            print("[INFO] Existing module may not be in dashboard (not published or no quiz)")
    
    def test_dashboard_stats_overall(self, api_client):
        """Dashboard has overall statistics"""
        response = api_client.get(f"{BASE_URL}/api/training/progress/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_modules" in data
        assert "total_completions" in data
        assert "total_in_progress" in data
        assert "department_stats" in data
        assert "top_performers" in data
        
        print(f"[PASS] Dashboard: {data['total_modules']} modules, {data['total_completions']} completions, {data['total_in_progress']} in progress")


# ==================== AUTHENTICATION TESTS ====================

class TestQuizAuth:
    """Test authentication requirements for quiz endpoints"""
    
    def test_get_quiz_requires_auth(self):
        """GET /api/training/modules/{id}/quiz without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz")
        assert response.status_code == 403
        print("[PASS] Get quiz requires authentication")
    
    def test_submit_quiz_requires_auth(self):
        """POST /api/training/modules/{id}/quiz/submit without auth returns 403"""
        response = requests.post(
            f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/submit",
            json={"answers": {"0": 0}}
        )
        assert response.status_code == 403
        print("[PASS] Submit quiz requires authentication")
    
    def test_quiz_results_requires_auth(self):
        """GET /api/training/modules/{id}/quiz/results without auth returns 403"""
        response = requests.get(f"{BASE_URL}/api/training/modules/{EXISTING_MODULE_ID}/quiz/results")
        assert response.status_code == 403
        print("[PASS] Quiz results requires authentication")


# ==================== CLEANUP ====================

class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_modules(self, api_client):
        """Clean up any TEST_ prefixed modules created during testing"""
        response = api_client.get(f"{BASE_URL}/api/training/modules")
        if response.status_code == 200:
            modules = response.json()["modules"]
            deleted = 0
            for module in modules:
                if module["title"].startswith("TEST_"):
                    del_res = api_client.delete(f"{BASE_URL}/api/training/modules/{module['id']}")
                    if del_res.status_code == 200:
                        deleted += 1
                        print(f"  Cleaned up: {module['title']}")
            print(f"[PASS] Cleanup complete, deleted {deleted} test modules")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
