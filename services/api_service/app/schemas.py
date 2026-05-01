from pydantic import BaseModel, Field


class RestaurantCreateIn(BaseModel):
    name: str
    cuisine: list[str] = Field(default_factory=list)
    food: list[str] = Field(default_factory=list)
    open_hours_from: str | None = None
    open_hours_to: str | None = None
    image_url: str | None = None
    rating: float = 0


class RestaurantPatchIn(BaseModel):
    name: str | None = None
    cuisine: list[str] | None = None
    food: list[str] | None = None
    open_hours_from: str | None = None
    open_hours_to: str | None = None
    image_url: str | None = None
    rating: float | None = None


class FoodCreateIn(BaseModel):
    restaurant_id: int
    name: str
    description: str | None = None
    cuisine_type: str
    food_type: str
    price: float
    is_available: bool = True
    image_url: str | None = None


class FoodPatchIn(BaseModel):
    name: str | None = None
    description: str | None = None
    cuisine_type: str | None = None
    food_type: str | None = None
    price: float | None = None
    is_available: bool | None = None
    image_url: str | None = None
