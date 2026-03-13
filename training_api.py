"""
Credlocity Employee Training & Rules/Policies API
Supports: Training modules with step-by-step guides, Rules & Policies by department/area
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path
import io

training_router = APIRouter(prefix="/api/training")

db = None

def set_db(database):
    global db
    db = database


# Auth
from auth import decode_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        user = await db.team_members.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(user):
    if user.get("role") not in ["admin", "super_admin", "director", "manager"]:
        raise HTTPException(status_code=403, detail="Admin/Manager access required")


DEPARTMENTS = [
    "General", "Collections", "Sales", "Customer Support",
    "Legal", "Operations", "Management", "HR", "IT"
]


# ==================== TRAINING MODULES ====================

@training_router.get("/modules")
async def list_modules(
    department: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List training modules, optionally filtered"""
    query = {}
    if department:
        query["department"] = department
    if status:
        query["status"] = status
    modules = await db.training_modules.find(query, {"_id": 0}).sort("order", 1).to_list(length=200)
    return {"modules": modules}


@training_router.get("/modules/{module_id}")
async def get_module(module_id: str, user: dict = Depends(get_current_user)):
    """Get a single training module with all steps"""
    module = await db.training_modules.find_one({"id": module_id}, {"_id": 0})
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return module


@training_router.post("/modules")
async def create_module(data: dict, user: dict = Depends(get_current_user)):
    """Create a new training module"""
    require_admin(user)
    module = {
        "id": str(uuid4()),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "department": data.get("department", "General"),
        "content": data.get("content", ""),
        "steps": data.get("steps", []),
        "status": data.get("status", "draft"),
        "order": data.get("order", 0),
        "created_by": user["id"],
        "created_by_name": user.get("full_name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.training_modules.insert_one(module)
    module.pop("_id", None)
    return module


@training_router.put("/modules/{module_id}")
async def update_module(module_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Update a training module"""
    require_admin(user)
    data.pop("id", None)
    data.pop("_id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = user["id"]
    result = await db.training_modules.update_one({"id": module_id}, {"$set": data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Module not found")
    return {"message": "Module updated"}


@training_router.delete("/modules/{module_id}")
async def delete_module(module_id: str, user: dict = Depends(get_current_user)):
    """Delete a training module"""
    require_admin(user)
    result = await db.training_modules.delete_one({"id": module_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Module not found")
    return {"message": "Module deleted"}


# ==================== QUIZZES ====================

@training_router.get("/modules/{module_id}/quiz")
async def get_quiz(module_id: str, user: dict = Depends(get_current_user)):
    """Get quiz for a module"""
    quiz = await db.training_quizzes.find_one({"module_id": module_id}, {"_id": 0})
    if not quiz:
        return {"quiz": None}
    # For non-admin, strip correct answers
    if user.get("role") not in ["admin", "super_admin", "director", "manager"]:
        for q in quiz.get("questions", []):
            q.pop("correct_answer", None)
            q.pop("explanation", None)
    return {"quiz": quiz}


@training_router.post("/modules/{module_id}/quiz")
async def save_quiz(module_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Admin: create or update quiz for a module"""
    require_admin(user)
    module = await db.training_modules.find_one({"id": module_id}, {"_id": 0, "id": 1, "title": 1})
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    questions = data.get("questions", [])
    passing_score = data.get("passing_score", 80)

    # Validate questions
    for i, q in enumerate(questions):
        if not q.get("question"):
            raise HTTPException(status_code=400, detail=f"Question {i+1} text is required")
        if not q.get("options") or len(q["options"]) < 2:
            raise HTTPException(status_code=400, detail=f"Question {i+1} needs at least 2 options")
        if q.get("correct_answer") is None:
            raise HTTPException(status_code=400, detail=f"Question {i+1} needs a correct answer")

    now = datetime.now(timezone.utc).isoformat()
    existing = await db.training_quizzes.find_one({"module_id": module_id})

    quiz_data = {
        "module_id": module_id,
        "module_title": module.get("title", ""),
        "questions": questions,
        "passing_score": passing_score,
        "updated_at": now,
        "updated_by": user["id"]
    }

    if existing:
        await db.training_quizzes.update_one({"module_id": module_id}, {"$set": quiz_data})
    else:
        quiz_data["id"] = str(uuid4())
        quiz_data["created_at"] = now
        quiz_data["created_by"] = user["id"]
        await db.training_quizzes.insert_one(quiz_data)
        quiz_data.pop("_id", None)

    return {"message": "Quiz saved", "question_count": len(questions)}


@training_router.post("/modules/{module_id}/quiz/submit")
async def submit_quiz(module_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Employee: submit quiz answers and get scored"""
    quiz = await db.training_quizzes.find_one({"module_id": module_id}, {"_id": 0})
    if not quiz:
        raise HTTPException(status_code=404, detail="No quiz for this module")

    answers = data.get("answers", {})  # {question_index: selected_option_index}
    questions = quiz.get("questions", [])
    passing_score = quiz.get("passing_score", 80)

    correct = 0
    total = len(questions)
    results = []

    for i, q in enumerate(questions):
        user_answer = answers.get(str(i))
        is_correct = user_answer == q.get("correct_answer")
        if is_correct:
            correct += 1
        results.append({
            "question": q["question"],
            "user_answer": user_answer,
            "correct_answer": q["correct_answer"],
            "is_correct": is_correct,
            "explanation": q.get("explanation", ""),
            "options": q.get("options", [])
        })

    score = round((correct / total * 100) if total > 0 else 0, 1)
    passed = score >= passing_score

    now = datetime.now(timezone.utc).isoformat()

    # Save attempt
    attempt = {
        "id": str(uuid4()),
        "module_id": module_id,
        "quiz_id": quiz.get("id", ""),
        "user_id": user["id"],
        "user_name": user.get("full_name", ""),
        "user_email": user.get("email", ""),
        "answers": answers,
        "score": score,
        "correct_count": correct,
        "total_questions": total,
        "passed": passed,
        "passing_score": passing_score,
        "submitted_at": now
    }
    await db.quiz_attempts.insert_one(attempt)
    attempt.pop("_id", None)

    # If passed, update progress to complete (if steps are also done)
    if passed:
        progress = await db.training_progress.find_one(
            {"user_id": user["id"], "module_id": module_id}
        )
        if progress:
            await db.training_progress.update_one(
                {"user_id": user["id"], "module_id": module_id},
                {"$set": {"quiz_passed": True, "quiz_score": score, "updated_at": now}}
            )
        else:
            await db.training_progress.insert_one({
                "id": str(uuid4()),
                "user_id": user["id"],
                "user_name": user.get("full_name", ""),
                "user_email": user.get("email", ""),
                "module_id": module_id,
                "completed_steps": [],
                "total_steps": 0,
                "is_complete": False,
                "quiz_passed": True,
                "quiz_score": score,
                "started_at": now,
                "updated_at": now
            })

    return {
        "score": score,
        "correct": correct,
        "total": total,
        "passed": passed,
        "passing_score": passing_score,
        "results": results
    }


@training_router.get("/modules/{module_id}/quiz/results")
async def get_quiz_results(module_id: str, user: dict = Depends(get_current_user)):
    """Admin: get all quiz attempts for a module"""
    require_admin(user)
    attempts = await db.quiz_attempts.find(
        {"module_id": module_id}, {"_id": 0}
    ).sort("submitted_at", -1).to_list(length=500)

    # Stats
    if attempts:
        scores = [a["score"] for a in attempts]
        avg_score = round(sum(scores) / len(scores), 1)
        pass_count = sum(1 for a in attempts if a.get("passed"))
        pass_rate = round((pass_count / len(attempts)) * 100, 1)
    else:
        avg_score = 0
        pass_rate = 0

    return {
        "module_id": module_id,
        "total_attempts": len(attempts),
        "average_score": avg_score,
        "pass_rate": pass_rate,
        "attempts": attempts
    }


# ==================== RULES & POLICIES ====================

@training_router.get("/policies")
async def list_policies(
    department: Optional[str] = None,
    category: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List rules & policies, optionally filtered"""
    query = {}
    if department:
        query["department"] = department
    if category:
        query["category"] = category
    policies = await db.policies.find(query, {"_id": 0}).sort("order", 1).to_list(length=200)
    return {"policies": policies}


@training_router.get("/policies/{policy_id}")
async def get_policy(policy_id: str, user: dict = Depends(get_current_user)):
    """Get a single policy document"""
    policy = await db.policies.find_one({"id": policy_id}, {"_id": 0})
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@training_router.post("/policies")
async def create_policy(data: dict, user: dict = Depends(get_current_user)):
    """Create a new policy document"""
    require_admin(user)
    policy = {
        "id": str(uuid4()),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "department": data.get("department", "General"),
        "category": data.get("category", "General"),
        "content": data.get("content", ""),
        "sections": data.get("sections", []),
        "status": data.get("status", "draft"),
        "order": data.get("order", 0),
        "effective_date": data.get("effective_date", ""),
        "created_by": user["id"],
        "created_by_name": user.get("full_name", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.policies.insert_one(policy)
    policy.pop("_id", None)
    return policy


@training_router.put("/policies/{policy_id}")
async def update_policy(policy_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Update a policy document"""
    require_admin(user)
    data.pop("id", None)
    data.pop("_id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = user["id"]
    result = await db.policies.update_one({"id": policy_id}, {"$set": data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"message": "Policy updated"}


@training_router.delete("/policies/{policy_id}")
async def delete_policy(policy_id: str, user: dict = Depends(get_current_user)):
    """Delete a policy"""
    require_admin(user)
    result = await db.policies.delete_one({"id": policy_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"message": "Policy deleted"}


# ==================== DEPARTMENTS LIST ====================

@training_router.get("/departments")
async def list_departments(user: dict = Depends(get_current_user)):
    """Get available departments"""
    return {"departments": DEPARTMENTS}


# ==================== POLICY CATEGORIES ====================

@training_router.get("/policy-categories")
async def list_policy_categories(user: dict = Depends(get_current_user)):
    """Get distinct policy categories"""
    categories = await db.policies.distinct("category")
    defaults = ["General", "HR", "Compliance", "Operations", "Safety", "IT Security"]
    all_cats = sorted(set(defaults + (categories or [])))
    return {"categories": all_cats}


# ==================== PROGRESS TRACKING ====================

@training_router.get("/my-progress")
async def get_my_progress(user: dict = Depends(get_current_user)):
    """Get current user's progress across all modules"""
    records = await db.training_progress.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).to_list(length=500)

    # Build a map: module_id -> progress record
    progress_map = {}
    for r in records:
        progress_map[r["module_id"]] = r

    return {"progress": progress_map}


@training_router.post("/modules/{module_id}/progress")
async def update_progress(module_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Update progress on a training module (mark steps complete, mark module complete)"""
    module = await db.training_modules.find_one({"id": module_id}, {"_id": 0})
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    completed_steps = data.get("completed_steps", [])
    is_complete = data.get("is_complete", False)

    total_steps = len(module.get("steps", []))
    if total_steps > 0 and len(completed_steps) >= total_steps:
        is_complete = True

    now = datetime.now(timezone.utc).isoformat()

    existing = await db.training_progress.find_one(
        {"user_id": user["id"], "module_id": module_id}
    )

    if existing:
        update_data = {
            "completed_steps": completed_steps,
            "is_complete": is_complete,
            "updated_at": now,
            "total_steps": total_steps,
        }
        if is_complete and not existing.get("is_complete"):
            update_data["completed_at"] = now
        await db.training_progress.update_one(
            {"user_id": user["id"], "module_id": module_id},
            {"$set": update_data}
        )
    else:
        record = {
            "id": str(uuid4()),
            "user_id": user["id"],
            "user_name": user.get("full_name", user.get("name", "")),
            "user_email": user.get("email", ""),
            "module_id": module_id,
            "module_title": module.get("title", ""),
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "is_complete": is_complete,
            "started_at": now,
            "completed_at": now if is_complete else None,
            "updated_at": now
        }
        await db.training_progress.insert_one(record)
        record.pop("_id", None)

    return {
        "module_id": module_id,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "is_complete": is_complete
    }


@training_router.get("/modules/{module_id}/progress-report")
async def get_module_progress_report(module_id: str, user: dict = Depends(get_current_user)):
    """Admin: get completion stats for a specific module"""
    require_admin(user)
    module = await db.training_modules.find_one({"id": module_id}, {"_id": 0})
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    records = await db.training_progress.find(
        {"module_id": module_id}, {"_id": 0}
    ).to_list(length=500)

    completed_count = sum(1 for r in records if r.get("is_complete"))
    in_progress_count = sum(1 for r in records if not r.get("is_complete"))

    return {
        "module_id": module_id,
        "module_title": module.get("title", ""),
        "total_assigned": len(records),
        "completed": completed_count,
        "in_progress": in_progress_count,
        "employees": records
    }


@training_router.get("/progress/dashboard")
async def get_progress_dashboard(user: dict = Depends(get_current_user)):
    """Admin: get overall training completion stats"""
    require_admin(user)

    # All modules
    modules = await db.training_modules.find(
        {"status": "published"}, {"_id": 0, "id": 1, "title": 1, "department": 1, "steps": 1}
    ).to_list(length=200)

    # All progress records
    all_progress = await db.training_progress.find({}, {"_id": 0}).to_list(length=5000)

    # Build stats per module
    module_stats = []
    all_quizzes = await db.training_quizzes.find({}, {"_id": 0, "module_id": 1}).to_list(length=200)
    quiz_module_ids = {q["module_id"] for q in all_quizzes}
    all_attempts = await db.quiz_attempts.find({}, {"_id": 0}).to_list(length=5000)

    for mod in modules:
        mod_progress = [p for p in all_progress if p["module_id"] == mod["id"]]
        completed = sum(1 for p in mod_progress if p.get("is_complete"))
        has_quiz = mod["id"] in quiz_module_ids
        mod_attempts = [a for a in all_attempts if a["module_id"] == mod["id"]]
        avg_quiz = round(sum(a["score"] for a in mod_attempts) / len(mod_attempts), 1) if mod_attempts else None
        quiz_pass_rate = round(sum(1 for a in mod_attempts if a.get("passed")) / len(mod_attempts) * 100, 1) if mod_attempts else None

        module_stats.append({
            "module_id": mod["id"],
            "title": mod["title"],
            "department": mod.get("department", ""),
            "total_steps": len(mod.get("steps", [])),
            "employees_started": len(mod_progress),
            "employees_completed": completed,
            "completion_rate": round((completed / len(mod_progress) * 100) if mod_progress else 0, 1),
            "has_quiz": has_quiz,
            "avg_quiz_score": avg_quiz,
            "quiz_pass_rate": quiz_pass_rate,
            "quiz_attempts": len(mod_attempts)
        })

    # Department stats
    dept_stats = {}
    for ms in module_stats:
        dept = ms["department"]
        if dept not in dept_stats:
            dept_stats[dept] = {"total_modules": 0, "total_completions": 0, "total_started": 0}
        dept_stats[dept]["total_modules"] += 1
        dept_stats[dept]["total_completions"] += ms["employees_completed"]
        dept_stats[dept]["total_started"] += ms["employees_started"]

    # Top performers (most modules completed)
    user_completions = {}
    for p in all_progress:
        if p.get("is_complete"):
            uid = p["user_id"]
            if uid not in user_completions:
                user_completions[uid] = {"user_name": p.get("user_name", "Unknown"), "count": 0}
            user_completions[uid]["count"] += 1
    top_performers = sorted(user_completions.values(), key=lambda x: x["count"], reverse=True)[:10]

    return {
        "total_modules": len(modules),
        "total_completions": sum(1 for p in all_progress if p.get("is_complete")),
        "total_in_progress": sum(1 for p in all_progress if not p.get("is_complete")),
        "module_stats": module_stats,
        "department_stats": dept_stats,
        "top_performers": top_performers
    }


# ==================== TRAINING ASSIGNMENTS ====================

@training_router.post("/assignments")
async def create_assignments(data: dict, user: dict = Depends(get_current_user)):
    """Admin: assign a module to employees or a department"""
    require_admin(user)

    module_id = data.get("module_id")
    if not module_id:
        raise HTTPException(status_code=400, detail="module_id is required")

    module = await db.training_modules.find_one({"id": module_id}, {"_id": 0, "id": 1, "title": 1})
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    employee_ids = data.get("employee_ids", [])
    department = data.get("department")
    due_date = data.get("due_date", "")
    note = data.get("note", "")

    # If assigning by department, look up all team members in that department
    if department and not employee_ids:
        members = await db.team_members.find(
            {"department": department}, {"_id": 0, "id": 1, "full_name": 1, "email": 1}
        ).to_list(length=500)
        # Also check users collection
        users = await db.users.find(
            {"department": department}, {"_id": 0, "id": 1, "full_name": 1, "email": 1}
        ).to_list(length=500)
        all_members = members + users
        employee_ids = [m["id"] for m in all_members]

    if not employee_ids:
        raise HTTPException(status_code=400, detail="No employees found to assign")

    # Look up employee details
    created = []
    now = datetime.now(timezone.utc).isoformat()

    for eid in employee_ids:
        # Check if already assigned
        existing = await db.training_assignments.find_one(
            {"module_id": module_id, "employee_id": eid, "status": {"$ne": "cancelled"}}
        )
        if existing:
            continue

        # Look up employee name
        emp = await db.users.find_one({"id": eid}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})
        if not emp:
            emp = await db.team_members.find_one({"id": eid}, {"_id": 0, "id": 1, "full_name": 1, "email": 1})
        if not emp:
            continue

        assignment = {
            "id": str(uuid4()),
            "module_id": module_id,
            "module_title": module.get("title", ""),
            "employee_id": eid,
            "employee_name": emp.get("full_name", emp.get("name", "")),
            "employee_email": emp.get("email", ""),
            "department": department or "",
            "due_date": due_date,
            "note": note,
            "status": "assigned",
            "assigned_by": user["id"],
            "assigned_by_name": user.get("full_name", ""),
            "created_at": now,
            "updated_at": now
        }
        await db.training_assignments.insert_one(assignment)
        assignment.pop("_id", None)
        created.append(assignment)

        # Create notification for the employee
        notification = {
            "id": str(uuid4()),
            "recipient_id": eid,
            "recipient_type": "employee",
            "notification_type": "training_assigned",
            "title": "New Training Assigned",
            "message": f"You have been assigned: {module.get('title', '')}",
            "related_module_id": module_id,
            "priority": "high" if due_date else "normal",
            "action_url": f"/admin/training",
            "is_read": False,
            "created_at": now
        }
        await db.notifications.insert_one(notification)

    return {"created": len(created), "assignments": created}


@training_router.get("/assignments")
async def list_assignments(
    module_id: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Admin: list all assignments with filters"""
    require_admin(user)
    query = {"status": {"$ne": "cancelled"}}
    if module_id:
        query["module_id"] = module_id
    if department:
        query["department"] = department
    if status:
        query["status"] = status

    assignments = await db.training_assignments.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=500)

    # Enrich with progress data
    for a in assignments:
        progress = await db.training_progress.find_one(
            {"user_id": a["employee_id"], "module_id": a["module_id"]}, {"_id": 0}
        )
        if progress:
            a["completed_steps"] = len(progress.get("completed_steps", []))
            a["total_steps"] = progress.get("total_steps", 0)
            a["is_complete"] = progress.get("is_complete", False)
            if progress.get("is_complete"):
                a["status"] = "completed"
        else:
            a["completed_steps"] = 0
            a["total_steps"] = 0
            a["is_complete"] = False

        # Check overdue
        if a.get("due_date") and not a.get("is_complete"):
            try:
                due = datetime.fromisoformat(a["due_date"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > due:
                    a["status"] = "overdue"
            except (ValueError, TypeError):
                pass

    return {"assignments": assignments}


@training_router.get("/my-assignments")
async def get_my_assignments(user: dict = Depends(get_current_user)):
    """Employee: get modules assigned to me"""
    assignments = await db.training_assignments.find(
        {"employee_id": user["id"], "status": {"$ne": "cancelled"}}, {"_id": 0}
    ).sort("due_date", 1).to_list(length=100)

    # Enrich with progress
    for a in assignments:
        progress = await db.training_progress.find_one(
            {"user_id": user["id"], "module_id": a["module_id"]}, {"_id": 0}
        )
        if progress:
            a["completed_steps"] = len(progress.get("completed_steps", []))
            a["total_steps"] = progress.get("total_steps", 0)
            a["is_complete"] = progress.get("is_complete", False)
            if progress.get("is_complete"):
                a["status"] = "completed"
        else:
            a["completed_steps"] = 0
            a["total_steps"] = 0
            a["is_complete"] = False

        # Check overdue
        if a.get("due_date") and not a.get("is_complete"):
            try:
                due = datetime.fromisoformat(a["due_date"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > due:
                    a["status"] = "overdue"
            except (ValueError, TypeError):
                pass

    return {"assignments": assignments}


@training_router.put("/assignments/{assignment_id}")
async def update_assignment(assignment_id: str, data: dict, user: dict = Depends(get_current_user)):
    """Admin: update assignment (due date, note, status)"""
    require_admin(user)
    update = {}
    if "due_date" in data:
        update["due_date"] = data["due_date"]
    if "note" in data:
        update["note"] = data["note"]
    if "status" in data:
        update["status"] = data["status"]
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = await db.training_assignments.update_one({"id": assignment_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"message": "Assignment updated"}


@training_router.delete("/assignments/{assignment_id}")
async def delete_assignment(assignment_id: str, user: dict = Depends(get_current_user)):
    """Admin: cancel/remove an assignment"""
    require_admin(user)
    result = await db.training_assignments.update_one(
        {"id": assignment_id}, {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"message": "Assignment cancelled"}


@training_router.get("/employees")
async def search_employees(q: Optional[str] = "", user: dict = Depends(get_current_user)):
    """Search employees for assignment"""
    require_admin(user)
    if len(q) < 1:
        # Return all
        users_list = await db.users.find({}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1, "department": 1}).to_list(length=100)
        team_list = await db.team_members.find({}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1, "department": 1}).to_list(length=100)
    else:
        regex = {"$regex": q, "$options": "i"}
        users_list = await db.users.find(
            {"$or": [{"full_name": regex}, {"email": regex}]},
            {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1, "department": 1}
        ).to_list(length=50)
        team_list = await db.team_members.find(
            {"$or": [{"full_name": regex}, {"email": regex}]},
            {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1, "department": 1}
        ).to_list(length=50)

    # Dedupe by id
    seen = set()
    result = []
    for u in users_list + team_list:
        if u["id"] not in seen:
            seen.add(u["id"])
            result.append(u)
    return {"employees": result}


# ==================== CERTIFICATES ====================

def generate_certificate_pdf(cert_data: dict) -> bytes:
    """Generate a professional PDF certificate"""
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    w, h = landscape(letter)
    c = canvas.Canvas(buf, pagesize=landscape(letter))

    # Background
    c.setFillColor(HexColor("#FAFBFC"))
    c.rect(0, 0, w, h, fill=1, stroke=0)

    # Border
    c.setStrokeColor(HexColor("#10B981"))
    c.setLineWidth(4)
    c.rect(30, 30, w - 60, h - 60, fill=0, stroke=1)

    # Inner border
    c.setStrokeColor(HexColor("#D1FAE5"))
    c.setLineWidth(1.5)
    c.rect(40, 40, w - 80, h - 80, fill=0, stroke=1)

    # Top accent bar
    c.setFillColor(HexColor("#10B981"))
    c.rect(40, h - 100, w - 80, 60, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 28)
    c.drawCentredString(w / 2, h - 82, "CREDLOCITY")

    # Certificate title
    c.setFillColor(HexColor("#1F2937"))
    c.setFont("Helvetica", 14)
    c.drawCentredString(w / 2, h - 135, "CERTIFICATE OF COMPLETION")

    # Decorative line
    c.setStrokeColor(HexColor("#10B981"))
    c.setLineWidth(2)
    c.line(w / 2 - 100, h - 148, w / 2 + 100, h - 148)

    # "This certifies that"
    c.setFillColor(HexColor("#6B7280"))
    c.setFont("Helvetica", 12)
    c.drawCentredString(w / 2, h - 180, "This is to certify that")

    # Employee name
    c.setFillColor(HexColor("#111827"))
    c.setFont("Helvetica-Bold", 30)
    name = cert_data.get("employee_name", "Employee")
    c.drawCentredString(w / 2, h - 220, name)

    # Line under name
    c.setStrokeColor(HexColor("#D1D5DB"))
    c.setLineWidth(0.5)
    name_width = max(c.stringWidth(name, "Helvetica-Bold", 30), 250)
    c.line(w / 2 - name_width / 2 - 20, h - 228, w / 2 + name_width / 2 + 20, h - 228)

    # "has successfully completed"
    c.setFillColor(HexColor("#6B7280"))
    c.setFont("Helvetica", 12)
    c.drawCentredString(w / 2, h - 258, "has successfully completed the training module")

    # Module title
    c.setFillColor(HexColor("#10B981"))
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(w / 2, h - 292, cert_data.get("module_title", "Training Module"))

    # Department
    c.setFillColor(HexColor("#6B7280"))
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, h - 316, f"Department: {cert_data.get('department', 'General')}")

    # Quiz score
    score = cert_data.get("quiz_score")
    if score is not None:
        c.setFillColor(HexColor("#059669"))
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(w / 2, h - 345, f"Quiz Score: {score}%")

    # Date
    c.setFillColor(HexColor("#374151"))
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, h - 380, f"Completed on: {cert_data.get('completed_date', '')}")

    # Certificate ID
    c.setFillColor(HexColor("#9CA3AF"))
    c.setFont("Helvetica", 8)
    c.drawCentredString(w / 2, 55, f"Certificate ID: {cert_data.get('certificate_id', '')}  |  Verify at credlocity.com/verify")

    # Bottom accent
    c.setFillColor(HexColor("#10B981"))
    c.rect(40, 40, w - 80, 8, fill=1, stroke=0)

    c.save()
    buf.seek(0)
    return buf.getvalue()


@training_router.post("/modules/{module_id}/certificate")
async def generate_certificate(module_id: str, user: dict = Depends(get_current_user)):
    """Generate a certificate for a completed module (must have passed quiz)"""
    module = await db.training_modules.find_one({"id": module_id}, {"_id": 0})
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    # Check progress
    progress = await db.training_progress.find_one(
        {"user_id": user["id"], "module_id": module_id}, {"_id": 0}
    )

    quiz = await db.training_quizzes.find_one({"module_id": module_id}, {"_id": 0})

    if quiz and (not progress or not progress.get("quiz_passed")):
        raise HTTPException(status_code=400, detail="You must pass the quiz to get a certificate")

    if not quiz and (not progress or not progress.get("is_complete")):
        raise HTTPException(status_code=400, detail="You must complete the module to get a certificate")

    # Check if certificate already exists
    existing = await db.training_certificates.find_one(
        {"user_id": user["id"], "module_id": module_id}, {"_id": 0}
    )
    if existing:
        return existing

    now = datetime.now(timezone.utc).isoformat()
    cert = {
        "id": str(uuid4()),
        "user_id": user["id"],
        "user_name": user.get("full_name", user.get("name", "")),
        "user_email": user.get("email", ""),
        "module_id": module_id,
        "module_title": module.get("title", ""),
        "department": module.get("department", "General"),
        "quiz_score": progress.get("quiz_score") if progress else None,
        "completed_date": (progress.get("completed_at") or now)[:10],
        "issued_at": now
    }
    await db.training_certificates.insert_one(cert)
    cert.pop("_id", None)
    return cert


@training_router.get("/certificates")
async def list_my_certificates(user: dict = Depends(get_current_user)):
    """Get all certificates for the current user"""
    certs = await db.training_certificates.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("issued_at", -1).to_list(length=100)
    return {"certificates": certs}


@training_router.get("/certificates/{cert_id}/download")
async def download_certificate(cert_id: str, user: dict = Depends(get_current_user)):
    """Download a certificate as PDF"""
    cert = await db.training_certificates.find_one({"id": cert_id}, {"_id": 0})
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    # Only the owner or an admin can download
    if cert["user_id"] != user["id"] and user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    pdf_bytes = generate_certificate_pdf({
        "employee_name": cert.get("user_name", ""),
        "module_title": cert.get("module_title", ""),
        "department": cert.get("department", ""),
        "quiz_score": cert.get("quiz_score"),
        "completed_date": cert.get("completed_date", ""),
        "certificate_id": cert["id"]
    })

    filename = f"Credlocity_Certificate_{cert.get('module_title', 'Training').replace(' ', '_')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
