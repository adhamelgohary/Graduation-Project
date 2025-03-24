


@admin_doctors.route('/admin/doctors', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Get search query if present
    search_query = request.args.get('search', '')
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    if search_query:
        # If search query exists, filter results
        cursor.execute("""
            SELECT u.user_id, u.first_name, u.last_name, u.email, 
                   d.specialization, d.license_number, d.accepting_new_patients
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            WHERE u.user_type = 'doctor'
            AND (
                u.first_name LIKE %s OR 
                u.last_name LIKE %s OR 
                u.email LIKE %s OR 
                d.specialization LIKE %s OR 
                d.license_number LIKE %s
            )
            ORDER BY u.last_name, u.first_name
        """, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', 
              f'%{search_query}%', f'%{search_query}%'))
    else:
        # Otherwise get all doctors
        cursor.execute("""
            SELECT u.user_id, u.first_name, u.last_name, u.email, 
                   d.specialization, d.license_number, d.accepting_new_patients
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            WHERE u.user_type = 'doctor'
            ORDER BY u.last_name, u.first_name
        """)
    
    doctors = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return render_template('Admin_Portal/Doctors/manage_doctors.html', doctors=doctors, search_query=search_query)




xz 