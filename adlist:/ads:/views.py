# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from ads.models import Ad, Comment, Fav
from django.views import View
from django.views import generic
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from ads.util import OwnerListView, OwnerDetailView, OwnerCreateView, OwnerUpdateView, OwnerDeleteView
from django.http import HttpResponse
from django.core.files.uploadedfile import InMemoryUploadedFile
from ads.forms import CreateForm, CommentForm
from django.shortcuts import render
from ads.models import Ad
from django.views import View
from django.contrib.humanize.templatetags.humanize import naturaltime

from ads.utils import dump_queries

from django.db.models import Q

class AdListView(OwnerListView):
    model = Ad
    template_name = "ads/ad_list.html"

    def get(self, request):
        objects = Ad.objects.all()
        favorites = list()
        strval = request.GET.get("search", False)

        # Search
        if strval :
            # Simple title-only search
            # objects = Ad.objects.filter(title__contains=strval).select_related().order_by('-updated_at')[:10]

            # Multi-field search
            query = Q(title__contains=strval)
            query.add(Q(text__contains=strval), Q.OR)
            objects = Ad.objects.filter(query).select_related().order_by('-updated_at')[:10]
        else :
            # try both versions with > 4 s and watch the queries that happen
            objects = Ad.objects.all().order_by('-updated_at')[:10]
            # objects = Ad.objects.select_related().all().order_by('-updated_at')[:10]

        # Augment the ad_list
        for obj in objects:
            obj.natural_updated = naturaltime(obj.updated_at)

        # ctx = {'ad_list' : objects, 'search': strval}
        # retval = render(request, self.template_name, ctx)

        dump_queries()

        if request.user.is_authenticated:
            # rows = [{'id': 2}]  (A list of rows)
            rows = request.user.favorite_ads.values('id')
            favorites = [ row['id'] for row in rows ]
        ctx = {'ad_list' : objects, 'favorites': favorites, 'search': strval}
        return render(request, self.template_name, ctx)


class AdDetailView(OwnerDetailView):
    model = Ad
    template_name = "ads/ad_detail.html"
    def get(self, request, pk) :
        ad = Ad.objects.get(id=pk)
        comments = Comment.objects.filter(forum=ad).order_by('-updated_at')
        comment_form = CommentForm()
        context = { 'ad' : ad, 'comments': comments, 'comment_form': comment_form }
        return render(request, self.template_name, context)

class AdCreateView(LoginRequiredMixin, View):
    # model = Ad
    # fields = ['title', 'text', 'price', 'picture']
    # template_name = "ads/ad_form.html"

    template = 'ads/ad_form.html'
    success_url = reverse_lazy('ads:all')
    def get(self, request, pk=None) :
        form = CreateForm()
        ctx = { 'form': form }
        return render(request, self.template, ctx)

    def post(self, request, pk=None) :
        form = CreateForm(request.POST, request.FILES or None)

        if not form.is_valid() :
            ctx = {'form' : form}
            return render(request, self.template, ctx)

        # Add owner to the model before saving
        ad = form.save(commit=False)
        ad.ads = self.request.user
        ad.save()
        return redirect(self.success_url)

class AdUpdateView(LoginRequiredMixin, View):
    model = Ad
    fields = ['title', 'text', 'price', 'picture']
    template_name = "ads/ad_form.html"

    template = 'ads/ad_form.html'
    success_url = reverse_lazy('ads:all')
    def get(self, request, pk) :
        ad = get_object_or_404(Ad, id=pk, ads=self.request.user)
        form = CreateForm(instance=ad)
        ctx = { 'form': form }
        return render(request, self.template, ctx)

    def post(self, request, pk=None) :
        ad = get_object_or_404(Ad, id=pk, ads=self.request.user)
        form = CreateForm(request.POST, request.FILES or None, instance=ad)

        if not form.is_valid() :
            ctx = {'form' : form}
            return render(request, self.template, ctx)

        ad.save()
        return redirect(self.success_url)

class AdDeleteView(OwnerDeleteView):
    model = Ad
    template_name = "ads/ad_delete.html"

def stream_file(request, pk) :
    ad = get_object_or_404(Ad, id=pk)
    response = HttpResponse()
    response['Content-Type'] = ad.content_type
    response['Content-Length'] = len(ad.picture)
    response.write(ad.picture)
    return response

# Another way to do it.
# This will handle create and update with an optional pk parameter on get and post
# We don't use the Generic or OwnerGeneric because (a) we need a form with a file
# and (b) we need to to populate the model with request.FILES
class AdFormView(LoginRequiredMixin, View):
    template = 'ads/ad_form.html'
    success_url = reverse_lazy('ads:all')
    def get(self, request, pk=None) :
        if not pk :
            form = CreateForm()
        else:
            ad = get_object_or_404(Ad, id=pk, ads=self.request.user)
            form = CreateForm(instance=ad)
        ctx = { 'form': form }
        return render(request, self.template, ctx)

    def post(self, request, pk=None) :
        if not pk:
            form = CreateForm(request.POST, request.FILES or None)
        else:
            ad = get_object_or_404(Ad, id=pk, ads=self.request.user)
            form = CreateForm(request.POST, request.FILES or None, instance=ad)

        if not form.is_valid() :
            ctx = {'form' : form}
            return render(request, self.template, ctx)

        # Adjust the model ads before saving
        ad = form.save(commit=False)
        ad.ads = self.request.user
        ad.save()
        return redirect(self.success_url)


class CommentCreateView(LoginRequiredMixin, View):
    def post(self, request, pk) :
        f = get_object_or_404(Ad, id=pk)
        comment_form = CommentForm(request.POST)

        comment = Comment(text=request.POST['comment'], ads=request.user, forum=f)
        comment.save()
        return redirect(reverse_lazy('ads:ad_detail', args=[pk]))

class CommentDeleteView(OwnerDeleteView):
    model = Comment
    template_name = "ads/comment_delete.html"

    # https://stackoverflow.com/questions/26290415/deleteview-with-a-dynamic-success-url-dependent-on-id
    def get_success_url(self):
        forum = self.object.forum
        return reverse_lazy('ads:ad_detail', args=[forum.id])

# https://stackoverflow.com/questions/16458166/how-to-disable-djangos-csrf-validation
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.utils import IntegrityError

@method_decorator(csrf_exempt, name='dispatch')
class AddFavoriteView(LoginRequiredMixin, View):
    def post(self, request, pk) :
        print("Add PK",pk)
        t = get_object_or_404(Ad, id=pk)
        ad = Fav(user=request.user, ad=t)
        try:
            ad.save()  # In case of duplicate key
        except IntegrityError as e:
            pass
        return HttpResponse()

@method_decorator(csrf_exempt, name='dispatch')
class DeleteFavoriteView(LoginRequiredMixin, View):
    def post(self, request, pk) :
        print("Delete PK",pk)
        t = get_object_or_404(Ad, id=pk)
        try:
            ad = Fav.objects.get(user=request.user, ad=t).delete()
        except Fav.DoesNotExist as e:
            pass

        return HttpResponse()
