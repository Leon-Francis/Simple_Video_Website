# coding='utf-8'
from . import admin
from flask import render_template, redirect, url_for, flash, session, request, abort
from app.admin.forms import LoginForm, TagForm, MovieForm, PwdForm, RoleForm, AdminForm
from app.models import Admin, Tag, Movie, User, Comment, Moviecol, Oplog, Adminlog, Userlog, Role
from functools import wraps
from app import db, app
from werkzeug.utils import secure_filename
import os, uuid, datetime
from werkzeug.security import generate_password_hash


# 上下文处理器，将变量转换为全局变量，用于在模板中显示时间
@admin.context_processor
def tpl_extra():
    date = dict(
        online_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    return date


# 访问控制装饰器
def admin_login_req(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print('111')
        if 'admin' not in session:
            return redirect(url_for('admin.login', next=request.url))
        return f(*args, **kwargs)

    return decorated_function





# 管理页面主页
@admin.route("/")
@admin_login_req
def index():
    return render_template('admin/index.html')


# 登录
@admin.route("/login/", methods=['GET', 'POST'])
def login():
    print('login')
    form = LoginForm()
    if form.validate_on_submit():  # 表单是否被提交
        data = form.data  # 字段名字和值组成的字典
        admin = Admin.query.filter_by(name=data['account']).first()  # first返回查询的第一个结果
        if not admin.check_pwd(data['pwd']):
            flash("密码错误！")
            return redirect(url_for('admin.login'))
        session['admin'] = data['account']  # 创建session
        session['admin_id'] = admin.id  # 保存管理员id，用来记录日志
        # 管理员登录日志
        adminlog = Adminlog(
            admin_id=admin.id,
            ip=request.remote_addr,
        )
        db.session.add(adminlog)
        db.session.commit()

        return redirect(request.args.get('next') or url_for('admin.index'))
    return render_template('admin/login.html', form=form)


# 登出
@admin.route("/logout/")
@admin_login_req
def logout():
    session.pop('admin', None)
    session.pop('admin_id', None)
    return redirect(url_for('admin.login'))


# 修改密码
@admin.route("/pwd/", methods=['GET', 'POST'])
@admin_login_req
def pwd():
    form = PwdForm()
    if form.validate_on_submit():
        data = form.data
        admin = Admin.query.filter_by(name=session['admin']).first()
        admin.pwd = generate_password_hash(data['new_pwd'])
        db.session.add(admin)
        db.session.commit()
        flash("修改成功！", 'ok')
        return redirect(url_for('admin.logout'))
    return render_template('admin/pwd.html', form=form)


# 添加标签
@admin.route("/tag/add/", methods=['GET', 'POST'])
@admin_login_req
def tag_add():
    form = TagForm()
    if form.validate_on_submit():
        data = form.data
        tag = Tag.query.filter_by(name=data['name']).count()
        if tag == 1:
            flash("名称已经存在", "err")
            return redirect(url_for('admin.tag_add'))
        tag = Tag(
            name=data['name']
        )
        db.session.add(tag)
        db.session.commit()
        flash("添加标签成功！", 'ok')
        # 添加日志
        oplog = Oplog(
            admin_id=session['admin_id'],
            ip=request.remote_addr,
            reason="添加标签{}".format(data['name'])
        )
        db.session.add(oplog)
        db.session.commit()
        redirect(url_for('admin.tag_add'))
    return render_template('admin/tag_add.html', form=form)


# 标签列表
@admin.route("/tag/list/<int:page>/", methods=['GET'])
@admin_login_req
def tag_list(page=None):
    if page is None:
        page = 1
    page_data = Tag.query.order_by(
        Tag.id.asc()
    ).paginate(page=page, per_page=10)

    temp_data = Tag.query.order_by(Tag.id.asc())

    play_data = {}

    for page in temp_data:
        play_data[page.id] = 0
        movies = Movie.query.filter_by(tag_id=page.id)
        for movie in movies:
            play_data[page.id] += movie.playnum

    return render_template('admin/tag_list.html', page_data=page_data, play_data=play_data)


# 标签删除
@admin.route("/tag/del/<int:id>/", methods=['GET'])
@admin_login_req
def tag_del(id=None):
    tag = Tag.query.filter_by(id=id).first_or_404()
    db.session.delete(tag)
    db.session.commit()
    flash("标签删除成功！", "ok")
    return redirect(url_for('admin.tag_list', page=1))


# 编辑标签
@admin.route("/tag/edit/<int:id>", methods=['GET', 'POST'])
@admin_login_req
def tag_edit(id=None):
    form = TagForm()
    tag = Tag.query.get_or_404(id)  # tag用作编辑页面显示初值
    if form.validate_on_submit():
        data = form.data
        tag_count = Tag.query.filter_by(name=data['name']).count()
        if tag.name == data['name'] and tag_count == 1:  # 如果名称修改了，且已存在
            flash("名称已经存在！", "err")
            return redirect(url_for('admin.tag_edit', id=id))
        tag.name = data['name']
        db.session.add(tag)
        db.session.commit()
        flash("修改标签成功！", 'ok')
        redirect(url_for('admin.tag_edit', id=id))
    return render_template('admin/tag_edit.html', form=form, tag=tag)  # tag用作编辑页面显示初值


# 修改文件名称为统一格式
def change_filename(filename):
    fileinfo = filename.split('.')
    filename = datetime.datetime.now().strftime('%Y%m%d%H%M%S') + str(uuid.uuid4().hex) + '.' +  fileinfo[-1]
    return filename


# 添加电影
@admin.route("/movie/add/", methods=['GET', 'POST'])
@admin_login_req
def movie_add():
    form = MovieForm()
    if form.validate_on_submit():
        data = form.data
        file_url = secure_filename(form.url.data.filename)  # 获取上传的电影文件名称
        file_logo = secure_filename(form.logo.data.filename)  # 获取上传的电影封面名称
        # 创建上传目录
        if not os.path.exists(app.config['UP_DIR']):
            os.makedirs(app.config['UP_DIR'])
            os.chmod(app.config['UP_DIR'], 0o666)
        # 修改文件名称为统一格式
        url = change_filename(file_url)
        logo = change_filename(file_logo)
        form.url.data.save(app.config['UP_DIR'] + url)
        form.logo.data.save(app.config['UP_DIR'] + logo)
        movie = Movie(
            title=data['title'],
            url=url,
            info=data['info'],
            logo=logo,
            star=int(data['star']),
            playnum=0,
            commentnum=0,
            tag_id=int(data['tag_id']),
            area=data['area'],
            release_time=data['release_time'],
            length=data['length']
        )
        db.session.add(movie)
        db.session.commit()
        flash("添加电影成功！", 'ok')
        return redirect(url_for('admin.movie_add'))
    return render_template('admin/movie_add.html', form=form)


# 电影列表
@admin.route("/movie/list/<int:page>", methods=['GET'])
@admin_login_req
def movie_list(page=None):
    if page is None:
        page = 1
    page_data = Movie.query.join(Tag).filter(  # 多表关联查询
        Tag.id == Movie.tag_id
    ).order_by(
        Movie.addtime.desc()
    ).paginate(page=page, per_page=10)
    return render_template('admin/movie_list.html', page_data=page_data)


# 电影删除
@admin.route("/movie/del/<int:id>/", methods=['GET'])
@admin_login_req
def movie_del(id=None):
    movie = Movie.query.filter_by(id=id).first_or_404()
    db.session.delete(movie)
    db.session.commit()
    flash("删除电影成功！", "ok")
    return redirect(url_for('admin.movie_list', page=1))


# 编辑电影
@admin.route("/movie/edit/<int:id>", methods=['GET', 'POST'])
@admin_login_req
def movie_edit(id=None):
    form = MovieForm()
    movie = Movie.query.get_or_404(id)  # movie用作编辑页面显示初值
    # 设置初值
    if request.method == 'GET':
        form.url.data = movie.url
        form.info.data = movie.info
        form.tag_id.data = movie.tag_id
        form.star.data = movie.star

    if form.validate_on_submit():
        data = form.data
        movie.count = Movie.query.filter_by(title=data['title']).count()
        if movie.count == 1 and movie.title != data['title']:
            flash("片名已存在", 'err')
            return redirect(url_for('admin.movie_edit'))

        if not os.path.exists(app.config['UP_DIR']):
            os.makedirs(app.config['UP_DIR'])
            os.chmod(app.config['UP_DIR'], 0o666)

        if form.url.data.filename != '':
            file_url = secure_filename(form.url.data.filename)
            movie.url = change_filename(file_url)
            form.url.data.save(app.config['UP_DIR'] + movie.url)

        if form.logo.data.filename != '':
            file_logo = secure_filename(form.logo.data.filename)
            movie.logo = change_filename(file_logo)
            form.logo.data.save(app.config['UP_DIR'] + movie.logo)

        movie.star = data['star']
        movie.tag_id = data['tag_id']
        movie.info = data['info']
        movie.title = data['title']
        movie.area = data['area']
        movie.length = data['length']
        movie.release_time = data['release_time']
        db.session.add(movie)
        db.session.commit()
        flash("编辑电影成功！", 'ok')
        redirect(url_for('admin.movie_edit', id=id))
    return render_template('admin/movie_edit.html', form=form, movie=movie)  # movie用作编辑页面显示初值


# 用户列表
@admin.route("/user/list/<int:page>/", methods=['GET'])
@admin_login_req
def user_list(page=None):
    if page is None:
        page = 1
    page_data = User.query.order_by(
        User.addtime.desc()
    ).paginate(page=page, per_page=1)
    return render_template('admin/user_list.html', page_data=page_data)


# 用户详情
@admin.route("/user/view/<int:id>", methods=['GET'])
@admin_login_req
def user_view(id=None):
    user = User.query.get_or_404(int(id))
    return render_template('admin/user_view.html', user=user)


# 删除用户
@admin.route("/user/del/<int:id>/", methods=['GET'])
@admin_login_req
def user_del(id=None):
    user = User.query.filter_by(id=id).first_or_404()
    db.session.delete(user)
    db.session.commit()
    flash("删除用户成功！", "ok")
    return redirect(url_for('admin.user_list', page=1))


# 评论列表
@admin.route("/comment/list/<int:page>/", methods=['GET'])
@admin_login_req
def comment_list(page):
    if page is None:
        page = 1
    page_data = Comment.query.join(
        Movie
    ).join(
        User
    ).filter(
        Movie.id == Comment.movie_id,
        User.id == Comment.user_id
    ).order_by(
        Comment.addtime.desc()
    ).paginate(page=page, per_page=10)

    return render_template('admin/comment_list.html', page_data=page_data)


# 删除评论
@admin.route("/comment/del/<int:id>/", methods=['GET'])
@admin_login_req
def comment_del(id=None):
    comment = Comment.query.filter_by(id=id).first_or_404()
    db.session.delete(comment)
    db.session.commit()
    flash("删除评论成功！", "ok")
    return redirect(url_for('admin.comment_list', page=1))


# 收藏列表
@admin.route("/moviecol/list/<int:page>/", methods=['GET'])
@admin_login_req
def moviecol_list(page=None):
    if page is None:
        page = 1
    page_data = Moviecol.query.join(
        Movie
    ).join(
        User
    ).filter(  # 多表关联查询
        Movie.id == Moviecol.movie_id,
        User.id == Moviecol.user_id
    ).order_by(
        Moviecol.addtime.desc()
    ).paginate(page=page, per_page=10)

    return render_template('admin/moviecol_list.html', page_data=page_data)


# 删除收藏
@admin.route("/moviecol/del/<int:id>/", methods=['GET'])
@admin_login_req
def moviecol_del(id=None):
    moviecol = Moviecol.query.filter_by(id=id).first_or_404()
    db.session.delete(moviecol)
    db.session.commit()
    flash("删除收藏成功！", "ok")
    return redirect(url_for('admin.moviecol_list', page=1))


# 操作日志
@admin.route("/oplog/list/<int:page>/", methods=['GET'])
@admin_login_req
def oplog_list(page=None):
    if page is None:
        page = 1
    page_data = Oplog.query.join(
        Admin
    ).filter(
        Admin.id == Oplog.admin_id
    ).order_by(
        Oplog.addtime.desc()
    ).paginate(page=page, per_page=10)
    return render_template('admin/oplog_list.html', page_data=page_data)


# 管理员登录日志
@admin.route("/adminloginlog/list/<int:page>/", methods=['GET'])
@admin_login_req
def adminloginlog_list(page=None):
    if page is None:
        page = 1
    page_data = Adminlog.query.join(
        Admin
    ).filter(
        Admin.id == Adminlog.admin_id
    ).order_by(
        Adminlog.addtime.desc()
    ).paginate(page=page, per_page=10)
    return render_template('admin/adminloginlog_list.html', page_data=page_data)


# 用户登录日志
@admin.route("/userloginlog/list/<int:page>/", methods=['GET'])
@admin_login_req
def userloginlog_list(page=None):
    if page is None:
        page = 1
    page_data = Userlog.query.join(
        User
    ).filter(
        User.id == Userlog.user_id
    ).order_by(
        Userlog.addtime.desc()
    ).paginate(page=page, per_page=10)
    return render_template('admin/userloginlog_list.html', page_data=page_data)


# 添加角色
@admin.route("/role/add/", methods=['GET', 'POST'])
@admin_login_req
def role_add():
    form = RoleForm()
    if form.validate_on_submit():
        data = form.data
        role = Role(
            name=data['name'],
        )

        db.session.add(role)
        db.session.commit()
        flash("添加角色成功！", 'ok')
        return redirect(url_for('admin.role_add'))
    return render_template('admin/role_add.html', form=form)


# 角色列表
@admin.route("/role/list/<int:page>/", methods=['GET'])
@admin_login_req
def role_list(page=None):
    if page is None:
        page = 1
    page_data = Role.query.order_by(
        Role.addtime.desc()
    ).paginate(page=page, per_page=10)
    return render_template('admin/role_list.html', page_data=page_data)


# 角色删除
@admin.route("/role/del/<int:id>/", methods=['GET'])
@admin_login_req
def role_del(id=None):
    role = Role.query.filter_by(id=id).first_or_404()
    db.session.delete(role)
    db.session.commit()
    flash("角色删除成功！", "ok")
    return redirect(url_for('admin.role_list', page=1))


# 编辑角色
@admin.route("/role/edit/<int:id>", methods=['GET', 'POST'])
@admin_login_req
def role_edit(id=None):
    form = RoleForm()
    role = Role.query.get_or_404(id)  # tag用作编辑页面显示初值
    if request.method == 'GET':
        form.name.data = role.name
    if form.validate_on_submit():
        data = form.data
        role.name = data['name'],
        db.session.add(role)
        db.session.commit()
        flash("修改角色成功！", 'ok')
        redirect(url_for('admin.role_edit', id=id))
    return render_template('admin/role_edit.html', form=form, role=role)  # role用作编辑页面显示初值



# 添加管理员
@admin.route("/admin/add/", methods=['GET', 'POST'])
@admin_login_req
def admin_add():
    form = AdminForm()
    if form.validate_on_submit():
        data = form.data
        admin = Admin(
            name=data['name'],
            pwd=generate_password_hash(data['pwd']),
            role_id=data['role_id'],
            is_super=1
        )
        db.session.add(admin)
        db.session.commit()
        flash('添加管理员成功！', 'ok')
        return redirect(url_for('admin.admin_add'))
    return render_template('admin/admin_add.html', form=form)


# 管理员列表
@admin.route("/admin/list/<int:page>/", methods=['GET'])
@admin_login_req
def admin_list(page=None):
    if page is None:
        page = 1
    page_data = Admin.query.join(
        Role
    ).filter(
        Role.id == Admin.role_id
    ).order_by(
        Admin.addtime.desc()
    ).paginate(page=page, per_page=10)
    return render_template('admin/admin_list.html', page_data=page_data)
