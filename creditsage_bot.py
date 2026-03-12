"""
CreditSage - AI Chatbot that learns from Credlocity website content
Only uses information from blogs, pages, and articles on the website
"""
from datetime import datetime, timezone
import uuid

class CreditSageBot:
    """
    AI Assistant trained only on Credlocity website content
    """
    
    def __init__(self, db):
        self.db = db
        self.knowledge_base = []
        
    async def index_website_content(self):
        """
        Index all content from the website to build knowledge base
        """
        knowledge = []
        
        # Index all published blog posts
        blog_posts = await self.db.blog_posts.find({"status": "published"}).to_list(length=None)
        for post in blog_posts:
            knowledge.append({
                "type": "blog",
                "title": post.get("title"),
                "content": post.get("content"),
                "excerpt": post.get("excerpt"),
                "url": f"/blog/{post.get('slug')}",
                "category": post.get("category"),
                "tags": post.get("tags", [])
            })
        
        # Index all published pages
        pages = await self.db.pages.find({"status": "published"}).to_list(length=None)
        for page in pages:
            knowledge.append({
                "type": "page",
                "title": page.get("title"),
                "content": page.get("content"),
                "excerpt": page.get("excerpt"),
                "url": f"/{page.get('slug')}",
                "slug": page.get("slug")
            })
        
        # Index reviews (for testimonials/success stories)
        reviews = await self.db.reviews.find({"featured_on_homepage": True}).to_list(length=None)
        for review in reviews:
            knowledge.append({
                "type": "review",
                "client_name": review.get("client_name"),
                "content": review.get("testimonial_text"),
                "points_improved": review.get("points_improved"),
                "service": review.get("service_used")
            })
        
        # Index FAQs if they exist
        faqs = await self.db.faqs.find({}).to_list(length=None) if hasattr(self.db, 'faqs') else []
        for faq in faqs:
            knowledge.append({
                "type": "faq",
                "question": faq.get("question"),
                "answer": faq.get("answer"),
                "category": faq.get("category")
            })
        
        self.knowledge_base = knowledge
        return len(knowledge)
    
    def search_knowledge(self, query):
        """
        Search through indexed content for relevant information
        Simple keyword-based search
        """
        query_lower = query.lower()
        results = []
        
        for item in self.knowledge_base:
            relevance = 0
            
            # Check title
            if item.get("title") and query_lower in item["title"].lower():
                relevance += 3
            
            # Check content
            if item.get("content") and query_lower in item["content"].lower():
                relevance += 2
            
            # Check excerpt
            if item.get("excerpt") and query_lower in item["excerpt"].lower():
                relevance += 1
            
            # Check question (for FAQs)
            if item.get("question") and query_lower in item["question"].lower():
                relevance += 4
            
            if relevance > 0:
                results.append({
                    **item,
                    "relevance": relevance
                })
        
        # Sort by relevance
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:5]  # Top 5 results
    
    def generate_response(self, query, context_items):
        """
        Generate a response based on the query and context
        This is a simple template-based response
        In production, this would use an LLM with the context
        """
        if not context_items:
            return {
                "response": "I apologize, but I don't have information about that specific topic on our website yet. Please feel free to contact our team directly, or check our blog and resources pages for more information.",
                "sources": []
            }
        
        # Build response with sources
        response_parts = [
            "Based on information from our website:\n\n"
        ]
        
        sources = []
        for item in context_items[:3]:  # Use top 3 results
            if item["type"] == "blog":
                response_parts.append(f"📝 From '{item['title']}': {item.get('excerpt', '')[:200]}...\n")
                sources.append({
                    "title": item["title"],
                    "url": item["url"],
                    "type": "blog"
                })
            elif item["type"] == "page":
                response_parts.append(f"📄 On our {item['title']} page: {item.get('excerpt', '')[:200]}...\n")
                sources.append({
                    "title": item["title"],
                    "url": item["url"],
                    "type": "page"
                })
            elif item["type"] == "faq":
                response_parts.append(f"❓ {item['question']}\n✅ {item['answer']}\n")
                sources.append({
                    "question": item["question"],
                    "type": "faq"
                })
            elif item["type"] == "review":
                response_parts.append(f"⭐ Success Story: {item['client_name']} improved their credit score by {item.get('points_improved', 'significantly')} points!\n")
        
        response_parts.append("\nWould you like to know more about any of these topics?")
        
        return {
            "response": "".join(response_parts),
            "sources": sources
        }
    
    async def chat(self, user_message, conversation_id=None):
        """
        Main chat function
        """
        # Search knowledge base
        relevant_content = self.search_knowledge(user_message)
        
        # Generate response
        result = self.generate_response(user_message, relevant_content)
        
        # Log conversation
        conversation = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id or str(uuid.uuid4()),
            "user_message": user_message,
            "bot_response": result["response"],
            "sources": result["sources"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db.creditsage_conversations.insert_one(conversation)
        
        return {
            **result,
            "conversation_id": conversation["conversation_id"]
        }
