from django.urls import path
from . import views, grading_views, coding_views, math_views, subscription_views, admin_dashboard_views

urlpatterns = [
    # Trang chủ & Học sinh
    path('', views.home_page, name='home'),
    path('thi-truc-tuyen/', views.online_exam, name='online_exam'),
    path('vao-thi/', views.enter_exam_code, name='enter_exam_code'),
    path('thi/<str:exam_code>/', views.take_exam, name='take_exam'),
    path('nop-bai/<str:exam_code>/', views.submit_exam, name='submit_exam'),
    path('cham-phieu/', views.scan_sheet, name='scan_sheet'),

    # Bảng điều khiển Quản trị toàn hệ thống (Admin Dashboard & Portals)
    path('quan-tri/', admin_dashboard_views.admin_dashboard_view, name='admin_dashboard'),
    path('quan-tri/goi-dich-vu/', admin_dashboard_views.admin_plans_view, name='admin_plans'),
    path('quan-tri/goi-dich-vu/toggle/<int:plan_id>/', admin_dashboard_views.admin_toggle_plan, name='admin_toggle_plan'),
    path('quan-tri/thue-bao/gia-han/<int:sub_id>/', admin_dashboard_views.admin_extend_subscription, name='admin_extend_sub'),
    path('quan-tri/giao-dich/', admin_dashboard_views.admin_transactions_view, name='admin_transactions'),
    path('quan-tri/giao-dich/duyet/<int:tx_id>/', admin_dashboard_views.admin_approve_transaction, name='admin_approve_tx'),
    path('quan-tri/giao-dich/huy/<int:tx_id>/', admin_dashboard_views.admin_cancel_transaction, name='admin_cancel_tx'),
    path('quan-tri/ban-quyen/', admin_dashboard_views.admin_licenses_view, name='admin_licenses'),
    path('quan-tri/ban-quyen/gia-han/<int:license_id>/', admin_dashboard_views.admin_extend_license, name='admin_extend_license'),
    path('quan-tri/cai-dat/', admin_dashboard_views.admin_settings_view, name='admin_settings'),
    path('quan-tri/nguoi-dung/', views.user_management_view, name='admin_users'),

    # Xác thực & Hồ sơ người dùng (Auth & Profile)
    path('dang-nhap/', views.login_view, name='login'),
    path('dang-xuat/', views.logout_view, name='logout'),
    path('dang-ky/', views.register_view, name='register'),
    path('thong-tin-ca-nhan/', views.profile_view, name='profile'),
    path('api/cap-nhat-avatar/', views.api_update_avatar, name='api_update_avatar'),

    # Quản trị người dùng (Admin)
    path('quan-ly-nguoi-dung/', views.user_management_view, name='user_management'),
    path('api/doi-vai-tro/<int:user_id>/', views.update_user_role, name='update_user_role'),
    path('api/khoa-tai-khoan/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),

    # Quản lý Ngân hàng đề & Câu hỏi (Quản lý / Admin)
    path('ngan-hang-de/', views.manage_question_bank, name='manage_question_bank'),
    path('them-cau-hoi/', views.add_question, name='add_question'),
    path('nhap-cau-hoi-word/', views.import_word_questions, name='import_word'),
    path('tai-file-mau-word/', views.download_sample_word, name='download_sample_word'),
    path('sua-cau-hoi/<int:question_id>/', views.edit_question, name='edit_question'),

    # Quản lý Bài thi & Ma trận đề (Quản lý / Admin)
    path('tao-bai-thi/', views.create_exam, name='create_exam'),
    path('danh-sach-bai-thi/', views.exam_list, name='exam_list'),
    path('chi-tiet-bai-thi/<int:quiz_id>/', views.exam_detail, name='exam_detail'),
    path('danh-sach-ket-qua-thi/<int:quiz_id>/', views.exam_results_view, name='exam_results_view'),
    path('api/xoa-bai-thi/<int:quiz_id>/', views.delete_exam, name='delete_exam'),
    path('api/matrix-data/', views.get_matrix_data, name='get_matrix_data'),
    path('xuat-ma-tran-word/<int:quiz_id>/', views.export_matrix_word, name='export_matrix_word'),
    path('xuat-ma-tran-excel/<int:quiz_id>/', views.export_matrix_excel, name='export_matrix_excel'),

    # =====================================================================
    # PHÂN HỆ CHẤM TRẮC NGHIỆM (GRADING SYSTEM)
    # =====================================================================
    path('cham-trac-nghiem/', grading_views.grading_dashboard, name='grading_dashboard'),
    path('cham-trac-nghiem/ky-thi/', grading_views.grading_manage_exams, name='grading_manage_exams'),
    path('cham-trac-nghiem/api/tao-ky-thi/', grading_views.api_create_exam_period, name='api_create_exam_period'),
    path('cham-trac-nghiem/api/tao-mon-thi/', grading_views.api_create_subject, name='api_create_subject'),
    path('cham-trac-nghiem/api/sua-mon-thi/<int:subject_id>/', grading_views.api_update_subject, name='api_update_subject'),
    path('cham-trac-nghiem/api/xoa-ky-thi/<int:period_id>/', grading_views.api_delete_exam_period, name='api_delete_exam_period'),
    path('cham-trac-nghiem/api/xoa-mon-thi/<int:subject_id>/', grading_views.api_delete_subject, name='api_delete_subject'),

    # Master Student Management
    path('cham-trac-nghiem/hoc-sinh/', grading_views.master_students_view, name='master_students_view'),
    path('cham-trac-nghiem/api/tao-lop/', grading_views.api_create_class, name='api_create_class'),
    path('cham-trac-nghiem/api/tao-hoc-sinh/', grading_views.api_create_student, name='api_create_student'),
    path('cham-trac-nghiem/api/sua-hoc-sinh/<int:student_pk>/', grading_views.api_update_student, name='api_update_student'),
    path('cham-trac-nghiem/api/xoa-hoc-sinh/<int:student_pk>/', grading_views.api_delete_student, name='api_delete_student'),
    path('cham-trac-nghiem/api/tim-hoc-sinh/', grading_views.api_search_student_by_sbd, name='api_search_student_by_sbd'),
    path('cham-trac-nghiem/api/nhap-hoc-sinh-excel/', grading_views.api_import_students_excel, name='api_import_students_excel'),
    path('cham-trac-nghiem/xuat-hoc-sinh-excel/', grading_views.export_students_excel, name='export_students_excel'),
    path('cham-trac-nghiem/tai-mau-hoc-sinh-excel/', grading_views.download_sample_student_excel, name='download_sample_student_excel'),

    # Đáp Án Chuẩn, Import Excel & Lưới Ma Trận
    path('cham-trac-nghiem/dap-an/', grading_views.grading_key_list, name='grading_key_list'),
    path('cham-trac-nghiem/dap-an/tao/', grading_views.grading_key_form, name='grading_key_create'),
    path('cham-trac-nghiem/dap-an/sua/<int:key_id>/', grading_views.grading_key_form, name='grading_key_edit'),
    path('cham-trac-nghiem/api/luu-dap-an/', grading_views.api_save_grading_key, name='api_save_grading_key'),
    path('cham-trac-nghiem/api/xoa-dap-an/<int:key_id>/', grading_views.api_delete_grading_key, name='api_delete_grading_key'),
    path('cham-trac-nghiem/api/xoa-hang-loat-dap-an/', grading_views.api_batch_delete_grading_keys, name='api_batch_delete_grading_keys'),
    path('cham-trac-nghiem/api/lay-cau-hoi/<int:key_id>/', grading_views.api_get_exam_key_questions, name='api_get_exam_key_questions'),
    path('cham-trac-nghiem/tai-mau-dap-an-excel/', grading_views.download_sample_key_excel, name='download_sample_key_excel'),
    path('cham-trac-nghiem/api/nhap-dap-an-excel/', grading_views.api_import_keys_excel, name='api_import_keys_excel'),
    path('cham-trac-nghiem/luoi-ma-tran/', grading_views.matrix_grid_view, name='matrix_grid_view'),
    path('cham-trac-nghiem/luoi-ma-tran/<int:subject_id>/', grading_views.matrix_grid_view, name='matrix_grid_view_subject'),

    # Chấm Bài & Xử Lý Ảnh JPG/TIFF 150 DPI
    path('cham-trac-nghiem/cham-bai/', grading_views.grading_sheet_view, name='grading_sheet_view'),
    path('cham-trac-nghiem/api/cham-bai/', grading_views.api_grade_submission, name='api_grade_submission'),
    path('cham-trac-nghiem/api/xu-ly-anh-phieu/', grading_views.api_process_sheet_image, name='api_process_sheet_image'),

    path('cham-trac-nghiem/mon-thi/<int:subject_id>/', grading_views.subject_workspace_view, name='subject_workspace_view'),
    path('cham-trac-nghiem/ky-thi/<int:period_id>/bang-diem/', grading_views.period_scorecard_view, name='period_scorecard'),
    path('cham-trac-nghiem/ky-thi/bang-diem/xuat-excel/', grading_views.export_aggregated_scorecard_excel, name='export_aggregated_scorecard_excel'),
    path('cham-trac-nghiem/xuat-pdf/<int:subject_id>/', grading_views.export_grading_results_pdf, name='export_grading_results_pdf'),
    path('cham-trac-nghiem/xuat-zip-anh/<int:subject_id>/', grading_views.export_grading_images_zip, name='export_grading_images_zip'),

    # Kết Quả & Xuất Bảng Điểm Excel
    path('cham-trac-nghiem/ket-qua/', grading_views.grading_results_list, name='grading_results_list'),
    path('cham-trac-nghiem/api/chi-tiet-bai-cham/<int:record_id>/', grading_views.api_get_grading_record_detail, name='api_get_grading_record_detail'),
    path('cham-trac-nghiem/api/cham-lai/<int:record_id>/', grading_views.api_regrade_record, name='api_regrade_record'),
    path('cham-trac-nghiem/api/tai-anh-bai-cham/<int:record_id>/', grading_views.api_upload_record_image, name='api_upload_record_image'),
    path('cham-trac-nghiem/api/xoa-bai-cham/<int:record_id>/', grading_views.api_delete_grading_record, name='api_delete_grading_record'),
    path('cham-trac-nghiem/xuat-excel/', grading_views.export_grading_results_excel, name='export_grading_results_excel'),

    # =====================================================================
    # PHÂN HỆ LUYỆN CODE (CODING PRACTICE)
    # =====================================================================
    path('luyen-code/', coding_views.coding_list_view, name='coding_list'),
    path('luyen-code/quan-ly/', coding_views.coding_manage_list, name='coding_manage_list'),
    path('luyen-code/quan-ly/export/', coding_views.coding_export_json, name='coding_export_json'),
    path('luyen-code/quan-ly/import/', coding_views.coding_import_json, name='coding_import_json'),
    path('luyen-code/ky-thi/', coding_views.coding_exam_list, name='coding_exam_list'),
    path('luyen-code/ky-thi/them/', coding_views.coding_exam_create, name='coding_exam_create'),
    path('luyen-code/ky-thi/<int:exam_id>/sua/', coding_views.coding_exam_edit, name='coding_exam_edit'),
    path('luyen-code/ky-thi/<int:exam_id>/xoa/', coding_views.coding_exam_delete, name='coding_exam_delete'),
    path('luyen-code/ky-thi/<int:exam_id>/', coding_views.coding_exam_detail, name='coding_exam_detail'),
    path('luyen-code/ky-thi/<int:exam_id>/export/', coding_views.coding_exam_export_json, name='coding_exam_export_json'),
    path('luyen-code/ky-thi/<int:exam_id>/import/', coding_views.coding_exam_import_json, name='coding_exam_import_json'),
    path('luyen-code/ky-thi/<int:exam_id>/ket-qua/', coding_views.coding_exam_results, name='coding_exam_results'),
    path('luyen-code/ky-thi/<int:exam_id>/dang-ky/', coding_views.coding_exam_register, name='coding_exam_register'),
    path('luyen-code/ky-thi/<int:exam_id>/quan-ly-dang-ky/', coding_views.coding_manage_registrations, name='coding_manage_registrations'),
    path('api/luyen-code/ky-thi/duyet/', coding_views.api_coding_approve_registration, name='api_coding_approve_registration'),
    path('luyen-code/them/', coding_views.coding_create, name='coding_create'),
    path('luyen-code/sua/<int:question_id>/', coding_views.coding_edit, name='coding_edit'),
    path('luyen-code/xoa/<int:question_id>/', coding_views.coding_delete_question, name='coding_delete_question'),
    path('luyen-code/sua/<int:question_id>/toggle/', coding_views.coding_toggle_attr, name='coding_toggle_attr'),
    path('luyen-code/sua/<int:question_id>/auto-testcase/', coding_views.coding_auto_testcase, name='coding_auto_testcase'),
    path('luyen-code/testcase/<int:testcase_id>/cap-nhat-diem/', coding_views.coding_update_single_tc_points, name='coding_update_single_tc_points'),
    path('luyen-code/<int:question_id>/testcase/cap-nhat-diem/', coding_views.coding_update_testcase_points, name='coding_update_testcase_points'),
    path('luyen-code/testcase/<int:testcase_id>/xoa/', coding_views.coding_delete_testcase, name='coding_delete_testcase'),
    path('luyen-code/<str:question_code>/', coding_views.coding_detail_view, name='coding_detail'),
    path('luyen-code/<str:question_code>/binh-luan/', coding_views.add_coding_comment, name='add_coding_comment'),
    path('api/luyen-code/<str:question_code>/submit/', coding_views.submit_code_api, name='submit_code_api'),
    path('api/luyen-code/ket-qua/code/<int:submission_id>/', coding_views.api_get_submission_code, name='api_get_submission_code'),

    # Chuyển đổi tài liệu Toán học (Ảnh/PDF -> Word LaTeX)
    path('chuyen-doi-tai-lieu/', math_views.math_converter_view, name='math_converter'),
    path('api/chuyen-doi-tai-lieu/convert/', math_views.api_convert_math_doc, name='api_convert_math_doc'),
    path('chuyen-doi-tai-lieu/tai-ve/<int:conversion_id>/', math_views.download_converted_docx, name='download_converted_docx'),
    path('chuyen-doi-tai-lieu/chi-tiet/<int:conversion_id>/', math_views.get_conversion_detail, name='get_conversion_detail'),
    path('chuyen-doi-tai-lieu/xoa/<int:conversion_id>/', math_views.delete_conversion_history, name='delete_conversion_history'),

    # THƯƠNG MẠI HOÁ (BẢNG GIÁ, GÓI DỊCH VỤ & THANH TOÁN QR)
    path('bang-gia/', subscription_views.pricing_view, name='pricing'),
    path('thanh-toan/<slug:plan_code>/', subscription_views.checkout_view, name='checkout'),
    path('api/thanh-toan/kiem-tra/<str:tx_code>/', subscription_views.api_check_payment_status, name='api_check_payment'),
    path('thanh-toan/gia-lap/<str:tx_code>/', subscription_views.simulate_payment_success, name='simulate_payment'),
]
