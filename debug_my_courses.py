
import sys
import os
from sqlalchemy import text
from src.config import engine

def debug_my_courses(user_id):
    with engine.connect() as conn:
        print(f"--- Debugging Courses for User {user_id} ---")
        
        # 1. Direct Enrollments
        print("\n1. Direct Enrollments (table 'enrollments'):")
        stmt = text("""
            SELECT e.course_id, c.title, e.is_active 
            FROM enrollments e 
            JOIN courses c ON e.course_id = c.id
            WHERE e.user_id = :uid
        """)
        rows = conn.execute(stmt, {"uid": user_id}).fetchall()
        if not rows:
            print("  No direct enrollments.")
        for r in rows:
            print(f"  - Course {r.course_id} ('{r.title}'): Active={r.is_active}")

        # 2. Group Memberships
        print("\n2. Group Memberships (table 'group_students'):")
        stmt = text("""
            SELECT gs.group_id, g.name
            FROM group_students gs 
            JOIN groups g ON gs.group_id = g.id
            WHERE gs.student_id = :uid
        """)
        group_rows = conn.execute(stmt, {"uid": user_id}).fetchall()
        if not group_rows:
            print("  No group memberships.")
        
        group_ids = []
        for r in group_rows:
            print(f"  - Group {r.group_id} ('{r.name}')")
            group_ids.append(r.group_id)
        
        # 3. Group Course Access
        if group_ids:
            print(f"\n3. Course Access via Groups {group_ids} (table 'course_group_access'):")
            # Need to handle empty tuple for SQL IN clause
            if len(group_ids) == 1:
                group_ids_tuple = f"({group_ids[0]})"
            else:
                group_ids_tuple = tuple(group_ids)
                
            stmt = text(f"""
                SELECT cga.group_id, cga.course_id, c.title, cga.is_active as access_active, c.is_active as course_active
                FROM course_group_access cga 
                JOIN courses c ON cga.course_id = c.id
                WHERE cga.group_id IN {group_ids_tuple}
            """)
            rows = conn.execute(stmt).fetchall()
            if not rows:
                print("  No courses linked to these groups.")
            for r in rows:
                print(f"  - Group {r.group_id} -> Course {r.course_id} ('{r.title}'): AccessActive={r.access_active}, CourseActive={r.course_active}")
        
        # 4. Check active courses that should appear
        # The Python code does: 
        # combined_course_ids = enrolled + group_access
        # courses = FILTER(Course.is_active == True)
        
        print("\nSUMMARY (What should appear):")
        # Reuse logic? basically UNION of active things.

    print("\n--- 5. Test Route Logic via SQLAlchemy ---")
    from sqlalchemy.orm import sessionmaker
    # from src.config import engine # REMOVED to avoid UnboundLocalError
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    from src.schemas.models import Enrollment, GroupStudent, CourseGroupAccess, Course, Module, UserInDB
    from sqlalchemy import union, func
    
    # Logic from route
    # Get enrolled course IDs
    enrolled_docs = db.query(Enrollment.course_id).filter(
        Enrollment.user_id == user_id,
        Enrollment.is_active == True
    )
    # Note: route uses .subquery() immediately?
    enrolled_course_ids = enrolled_docs.subquery()
    
    # Get group access course IDs
    student_group_ids = db.query(GroupStudent.group_id).filter(
        GroupStudent.student_id == user_id
    ).subquery()
    
    group_course_ids = db.query(CourseGroupAccess.course_id).filter(
        CourseGroupAccess.group_id.in_(student_group_ids),
        CourseGroupAccess.is_active == True
    ).subquery()
    
    # Combine both sets of course IDs
    # Use UNION to combine both queries
    
    # Check what route does:
    # combined_course_ids = db.query(union(enrolled_course_ids.select(), group_course_ids.select()).alias('course_id')).subquery()
    
    # It seems route code does: 
    stmt = union(
        enrolled_course_ids.select(),
        group_course_ids.select()
    ).alias('course_id') # Does alias work on union result?
    
    combined_course_ids = db.query(stmt).subquery()
    
    # But wait, db.query(union(...)) ? 
    # Usually: db.query(column).filter(...)
    
    # If I copy paste the route logic exactly:
    try:
        q_enrolled = db.query(Enrollment.course_id).filter(Enrollment.user_id == user_id, Enrollment.is_active == True)
        q_group = db.query(CourseGroupAccess.course_id).join(GroupStudent, GroupStudent.group_id == CourseGroupAccess.group_id).filter(GroupStudent.student_id == user_id, CourseGroupAccess.is_active == True)
        
        u = union(q_enrolled, q_group)
        
        # Now select courses in u
        courses = db.query(Course).filter(Course.id.in_(u.select().subquery() if hasattr(u, 'select') else u)).all()
        
        print(f"Found {len(courses)} courses via simplified union:")
        for c in courses:
            print(f" - {c.id}: {c.title}")
            
    except Exception as e:
        print(f"Error in python logic: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    # Add src to path
    sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
    if len(sys.argv) > 1:
        debug_my_courses(int(sys.argv[1]))
    else:
        print("Provide user_id")
